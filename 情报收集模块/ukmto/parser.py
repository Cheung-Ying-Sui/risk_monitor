"""Pure HTML parsing. Missing or ambiguous source facts remain null/unknown."""

import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from lxml import etree, html

from .client import FEED_URL, LIST_URL, FetchError, validate_source_url
from .models import IncidentLink, ParsedUKMTOIncident


class ParseError(ValueError):
    pass


TYPES = {
    "suspicious activity": "suspicious_activity",
    "military interaction": "military_interaction",
    "hijack": "hijack",
    "hijacking": "hijack",
    "attack": "attack",
    "advisory": "advisory",
}
NUMBER = re.compile(
    r"(?:UKMTO\s*(?:incident\s*)?(?:#|No\.?|number|[-:])\s*|"
    r"incident\s*(?:number|no\.?|#|reference)\s*[:#-]?\s*)"
    r"(\d{1,4}(?:\s*[/\-]\s*\d{1,4})?)\b", re.I,
)


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_url(url: str) -> str:
    validate_source_url(url)
    p = urlsplit(url)
    query = sorted((k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                   if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"})
    return urlunsplit(("https", "www.ukmto.org", p.path.rstrip("/") or "/", urlencode(query), p.fragment))


def document(markup: str):
    if not markup.strip():
        raise ParseError("Empty HTML document")
    try:
        root = html.fromstring(markup)
    except (etree.ParserError, ValueError) as exc:
        raise ParseError("Invalid HTML document") from exc
    title = " ".join(root.xpath("//title/text()"))
    text = clean(" ".join(root.itertext()))
    if (re.search(r"Cloudflare|Just a moment|Access denied|Attention Required", title, re.I)
            or "Sorry, you have been blocked" in text):
        raise ParseError("UKMTO access challenge detected; collection was stopped")
    return root


def content_root(root):
    for node in root.xpath("//script|//style|//nav|//footer|//noscript|//form|//aside"):
        node.drop_tree()
    nodes = root.xpath("//main|//*[@role='main']")
    return nodes[0] if nodes else root


def has_dynamic_incidents(markup: str) -> bool:
    """Detect the official component by embedded semantics, not generated CSS class names."""
    root = document(markup)
    for value in root.xpath("//script[@id='__NEXT_DATA__']/text()"):
        try:
            data = json.loads(value)
        except ValueError as exc:
            raise ParseError("Invalid Next.js page data") from exc
        def contains_component(node):
            if isinstance(node, dict):
                return node.get("componentName") == "RecentIncident" or any(contains_component(v) for v in node.values())
            if isinstance(node, list):
                return any(contains_component(v) for v in node)
            return False
        if contains_component(data):
            return True
    return False


def extract_incident_links(markup: str, source_url: str) -> list[IncidentLink]:
    if has_dynamic_incidents(markup):
        raise ParseError("Dynamic RecentIncident page requires the official JSON feed; HTML count is a placeholder")
    root = content_root(document(markup))
    result = {}
    base = normalize_url(source_url)
    for anchor in root.xpath(".//a[@href]"):
        try:
            url = normalize_url(urljoin(source_url, anchor.get("href")))
        except (FetchError, ValueError):
            continue
        p = urlsplit(url)
        label = clean(anchor.text_content())
        # Semantics and stable URL paths first; never follow menu or third-party links.
        detail_path = bool(re.search(r"/(?:recent-incidents|incidents?)/[^/]+", p.path, re.I))
        semantic_label = bool(NUMBER.search(label) or re.search(
            r"\b(?:attack|suspicious activity|hijack|advisory|military interaction)\b", label, re.I))
        anchored = bool(p.fragment and p.fragment not in {"top", "main", "content"})
        if (url == base or re.search(r"\.(?:jpg|png|svg|pdf|zip)$", p.path, re.I)
                or not (detail_path or semantic_label or (anchored and NUMBER.search(label)))):
            continue
        result.setdefault(url, IncidentLink(url, label or None))
    if result:
        return list(result.values())
    text = clean(" ".join(root.itertext()))
    if re.search(r"\b(?:0\s+(?:reports|incidents)|no\s+(?:recent\s+)?incidents(?:\s+found)?)\b", text, re.I):
        return []
    raise ParseError("No incident links or explicit empty-state found; page structure may have changed")


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    value = clean(value)
    value = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", value, flags=re.I)
    normalized = re.sub(r"\s+(?:UTC|GMT)$", "+00:00", value, flags=re.I)
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)
    except ValueError:
        pass
    value = re.sub(r"\s+(?:UTC|GMT)$", "", value, flags=re.I)
    value = re.sub(r"\s+at\s+", " ", value, flags=re.I)
    for date_format in ("%d %B %Y", "%d %b %Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        for suffix in (" %H:%M:%S", " %H:%M", " %H%M", ""):
            try:
                return datetime.strptime(value, date_format + suffix).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    # Compact UKMTO DTG, with an explicit four-digit year only (no century guessing).
    try:
        return datetime.strptime(value.upper(), "%d%H%MZ %b %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_coordinates(text: str) -> tuple[float | None, float | None]:
    # Hemisphere coordinates: decimal degrees, degrees/minutes, or DMS.
    component = r"(\d{1,3}(?:\.\d+)?)\s*(?:[°º]\s*|\s+)?(?:(\d{1,2}(?:\.\d+)?)\s*['′]\s*)?(?:(\d{1,2}(?:\.\d+)?)\s*[\"″]\s*)?"
    match = re.search(component + r"([NS])\s*[,;/ ]+\s*" + component + r"([EW])\b", text, re.I)
    if match:
        d1, m1, s1, h1, d2, m2, s2, h2 = match.groups()
        if any(float(v or 0) >= 60 for v in (m1, s1, m2, s2)):
            return None, None
        lat = (float(d1) + float(m1 or 0) / 60 + float(s1 or 0) / 3600) * (-1 if h1.upper() == "S" else 1)
        lon = (float(d2) + float(m2 or 0) / 60 + float(s2 or 0) / 3600) * (-1 if h2.upper() == "W" else 1)
    else:
        latitude = re.search(r"\blat(?:itude)?\s*[:=]\s*([+-]?\d+(?:\.\d+)?)", text, re.I)
        longitude = re.search(r"\blon(?:gitude)?\s*[:=]\s*([+-]?\d+(?:\.\d+)?)", text, re.I)
        if not latitude or not longitude:
            return None, None
        lat, lon = float(latitude[1]), float(longitude[1])
    return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 else (None, None)


def _lines(root) -> list[str]:
    # Preserve boundaries even if field labels and values live in separate inline elements.
    copy = html.fromstring(html.tostring(root))
    for node in copy.iter():
        if node.tag in {"p", "div", "section", "article", "li", "tr", "dt", "dd", "h1", "h2", "h3", "br", "time"}:
            node.text = "\n" + (node.text or "")
            node.tail = "\n" + (node.tail or "")
        elif node.tag in {"td", "th"}:
            node.tail = " " + (node.tail or "")
    return [clean(line) for line in copy.text_content().splitlines() if clean(line)]


def _field(lines: list[str], *names: str) -> str | None:
    pattern = re.compile(r"^(?:" + "|".join(re.escape(n) for n in names) + r")\s*(?::|\s[-–]\s)\s*(.+)$", re.I)
    for index, line in enumerate(lines):
        match = pattern.match(line)
        if match:
            return match[1]
        if line.rstrip(":").lower() in names and index + 1 < len(lines):
            return lines[index + 1]
    return None


def content_hash(incident: ParsedUKMTOIncident) -> str:
    payload = incident.payload()
    record = incident.raw_payload.get("record", {})
    if record:
        payload["source_vessel_details"] = {key: record.get(key) for key in (
            "vesselName", "vesselUnderPirateControl", "dateVesselTaken", "crewHeld")}
    # Source formatting, transport metadata, and version-specific URLs are not changes in facts.
    for key in ("raw_payload", "content_hash", "source_url"):
        payload.pop(key)
    payload = {k: clean(v) if isinstance(v, str) else v for k, v in payload.items()}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def parse_incident(markup: str, source_url: str, title_hint: str | None = None) -> ParsedUKMTOIncident:
    root = document(markup)
    metadata = {n.get("property") or n.get("name"): n.get("content") for n in root.xpath("//meta[@content]")}
    root = content_root(root)
    fragment = urlsplit(source_url).fragment
    if fragment:
        nodes = root.xpath(".//*[@id=$fragment]", fragment=fragment)
        if not nodes:
            raise ParseError("Incident anchor is missing from source page")
        root = nodes[0]
    else:
        articles = root.xpath(".//article")
        if len(articles) == 1:
            root = articles[0]
    lines = _lines(root)
    headings = root.xpath(".//h1|.//h2")
    title = clean(headings[0].text_content()) if headings else (title_hint or metadata.get("og:title") or "")
    description = "\n".join(line for line in lines if line != title)
    if not title or not description:
        raise ParseError("Incident title or body is missing")
    if title.lower() in {"recent incidents", "page not found", "not found", "access denied"}:
        raise ParseError("Received a listing/error page instead of incident details")
    number_match = NUMBER.search(title) or NUMBER.search("\n".join(lines))
    number = re.sub(r"\s", "", number_match[1]) if number_match else None
    source_url = normalize_url(source_url)
    external_id = "UKMTO-" + number.replace("/", "-") if number else hashlib.sha256(source_url.encode()).hexdigest()
    type_text = _field(lines, "incident type", "type", "classification") or title
    kind = next((value for label, value in TYPES.items() if re.search(r"\b" + label + r"\b", type_text, re.I)), "unknown")
    location = _field(lines, "location", "position", "incident location")
    if not location:
        distance = re.search(r"\b\d+(?:\.\d+)?\s*(?:NM|nautical miles)\s+[^.\n]+", description, re.I)
        location = distance[0] if distance else None
    latitude, longitude = parse_coordinates(location or "")
    if latitude is None:
        latitude, longitude = parse_coordinates(description)
    incident_raw = _field(lines, "incident time", "time of incident", "date/time of incident", "incident date")
    published_raw = _field(lines, "published", "published at", "publication date", "date published") or metadata.get("article:published_time")
    if not published_raw:
        times = root.xpath(".//time[@datetime and (not(@itemprop) or @itemprop='datePublished')]/@datetime")
        published_raw = times[0] if times else None
    updated_raw = _field(lines, "last updated", "source updated", "updated at") or metadata.get("article:modified_time")
    raw_dates = {"incident_time": incident_raw, "published_at": published_raw, "source_updated_at": updated_raw}
    parsed_dates = {key: parse_datetime(value) for key, value in raw_dates.items()}
    warnings = [f"unparsed_{key}" for key, value in raw_dates.items() if value and not parsed_dates[key]]
    precision = "exact" if latitude is not None else "unknown"
    if location and re.search(r"(?:\d\s*NM\b|\bnautical miles\b|\bapproximately\b|\bapprox\b|\bvicinity\b)", location, re.I):
        precision = "approximate"
    precision_label = _field(lines, "location precision")
    if precision_label and precision_label.lower() in {"exact", "approximate", "region", "unknown"}:
        precision = precision_label.lower() if latitude is not None or precision_label.lower() != "exact" else "unknown"
    if not number:
        warnings.append("missing_incident_number_url_hash_used")
    source_type = (_field(lines, "source type", "reported by") or "unknown").lower().replace(" ", "_")
    verification = (_field(lines, "verification status") or "unknown").lower().replace(" ", "_")
    revision = re.search(r"\bUpdate\s*(\d+)\b", title, re.I)
    incident = ParsedUKMTOIncident(
        external_id=external_id, incident_number=number, incident_type=kind,
        title=title, description=description, source_url=source_url,
        location_text=location, latitude=latitude, longitude=longitude,
        location_precision=precision, region=_field(lines, "region"),
        vessel_type=_field(lines, "vessel type"),
        source_type=source_type if source_type in {"master", "company_security_officer", "military_authority", "third_party"} else "unknown",
        verification_status=verification if verification in {"verified", "unverified", "third_party"} else "unknown",
        casualties=_field(lines, "casualties"), environmental_impact=_field(lines, "environmental impact"),
        raw_payload={"html": markup, "text": "\n".join(lines), "raw_dates": raw_dates,
                     "warnings": warnings, "attribution": "UKMTO / Crown copyright", "parser_version": 1,
                     "update_number": int(revision[1]) if revision else 0},
        **parsed_dates,
    )
    incident.content_hash = content_hash(incident)
    return incident


def feed_records(data) -> list[dict]:
    if not isinstance(data, list):
        raise ParseError("Official incident feed must be a JSON array")
    # Non-UKMTO issuers are outside this module's scope. Malformed entries are left
    # for the per-item parser so one broken report cannot discard the whole feed.
    rows = [row for row in data if not isinstance(row, dict) or row.get("incidentIssuer", "UKMTO") == "UKMTO"]
    return sorted(rows, key=lambda row: str(row.get("utcDateOfIncident") or row.get("utcDateCreated") or "") if isinstance(row, dict) else "", reverse=True)


def feed_source_url(record: dict) -> str:
    identifier = record.get("sitecoreId") if isinstance(record, dict) else None
    if not isinstance(identifier, str) or not re.fullmatch(r"[a-fA-F0-9-]{36}", identifier):
        raise ParseError("Official incident is missing a valid stable sitecoreId")
    return LIST_URL + "#" + identifier.lower()


def parse_feed_incident(record: dict) -> ParsedUKMTOIncident:
    """Map the public API used by ukmto.org, retaining the complete official record."""
    if not isinstance(record, dict) or record.get("incidentIssuer") != "UKMTO":
        raise ParseError("Invalid UKMTO incident feed record")
    source_url = feed_source_url(record)
    body = record.get("otherDetails")
    if not isinstance(body, str) or not body.strip():
        raise ParseError("Official incident description is missing")
    # Paragraphs and all original description content remain in the stored description.
    description = "\n".join(clean(line) for line in body.splitlines() if clean(line))
    lines = description.splitlines()
    type_label = str(record.get("incidentTypeName") or "Unknown")
    incident_type = TYPES.get(type_label.lower(), "unknown")
    incident_time = parse_datetime(record.get("utcDateOfIncident"))
    published_at = parse_datetime(record.get("utcDateCreated"))
    number_value = record.get("incidentNumber")
    number = str(number_value).strip() if number_value is not None else None
    if number and not re.fullmatch(r"\d+", number):
        raise ParseError("Unexpected official incidentNumber format")
    # The official warning number restarts annually. Use an explicit report year
    # or source-provided incident/creation year; never use the collector clock.
    reference = re.search(r"UKMTO[\s_]+(?:WARNING|ADVISORY)[\s_]+(\d+)-(\d{2}(?:\d{2})?)\b", body, re.I)
    source_date = incident_time or published_at
    year = source_date.year if source_date else None
    if reference:
        number = str(int(reference[1]))
        report_year = reference[2]
        if len(report_year) == 4:
            year = int(report_year)
        elif year is not None:
            year = year // 100 * 100 + int(report_year)
    # If number exists but its annual scope is unavailable, prefer a stable URL hash
    # over accidentally merging two years' reports with the same sequence number.
    external_id = f"UKMTO-{year}-{int(number)}" if number and year else hashlib.sha256(source_url.encode()).hexdigest()
    title = lines[0] if reference and len(lines[0]) <= 200 else f"{type_label} UKMTO #{number or record['sitecoreId']}"
    location_match = re.search(r"\b\d+(?:\.\d+)?\s*(?:NM|nautical miles)\s+[^.]+", clean(body), re.I)
    location = location_match[0] if location_match else record.get("place") or None
    latitude, longitude = record.get("locationLatitude"), record.get("locationLongitude")
    warnings = []
    if (latitude is None or longitude is None or isinstance(latitude, bool) or isinstance(longitude, bool)):
        latitude = longitude = None
    else:
        try:
            latitude, longitude = float(latitude), float(longitude)
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise ValueError("out of range")
        except (ValueError, TypeError):
            warnings.append("invalid_source_coordinates")
            latitude = longitude = None
    precision = "approximate" if location_match else "exact" if latitude is not None else "region" if location else "unknown"
    if not number or not year:
        warnings.append("missing_incident_number_or_year_url_hash_used")
    for key, parsed in (("utcDateOfIncident", incident_time), ("utcDateCreated", published_at)):
        if record.get(key) and parsed is None:
            warnings.append(f"unparsed_{key}")
    revisions = re.findall(r"\bUPDATE\s*[-:]?\s*(\d+)\b", body, re.I)
    reporter = (_field(lines, "source") or "").lower()
    source_type = {"master": "master", "military authorities": "military_authority",
                   "military authority": "military_authority", "company security officer": "company_security_officer",
                   "third party": "third_party"}.get(reporter, "unknown")
    incident = ParsedUKMTOIncident(
        external_id=external_id, incident_number=(f"{number}-{year}" if number and year else number),
        incident_type=incident_type, title=title, description=description, source_url=source_url,
        incident_time=incident_time, published_at=published_at,
        location_text=location, latitude=latitude, longitude=longitude, location_precision=precision,
        region=record.get("region") or None, vessel_type=clean(record.get("vesselType") or "") or None,
        source_type=source_type,
        raw_payload={"record": record, "feed_url": FEED_URL, "warnings": warnings,
                     "attribution": "UKMTO / Crown copyright", "parser_version": 1,
                     "update_number": max(map(int, revisions)) if revisions else 0},
    )
    incident.content_hash = content_hash(incident)
    return incident

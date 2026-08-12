"""Conservative anchor resolution for JWLA boundary text."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from shapely.geometry import Point, mapping, shape
from shapely.geometry.base import BaseGeometry

from risk_zones.anchor_override_validator import validate_anchor_override
from risk_zones.geojson_loader import normalize_name


def normalize_anchor_name(name: str | None) -> str:
    return normalize_name(name).replace(" ", "_")


def load_anchor_overrides(path: str | Path) -> dict[str, Any]:
    override_path = Path(path)
    if not override_path.exists():
        raise FileNotFoundError(f"Anchor override file does not exist: {override_path}")
    with override_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict) or not isinstance(data.get("anchors"), dict):
        raise ValueError("Anchor override file must contain an anchors object")
    valid_anchors = {}
    invalid_anchors = {}
    validation_warnings = {}

    for key, anchor in data["anchors"].items():
        if not isinstance(anchor, dict):
            invalid_anchors[key] = {
                "anchor": anchor,
                "validation": {
                    "valid": False,
                    "errors": ["anchor_must_be_object"],
                    "warnings": [],
                },
            }
            continue

        validation = validate_anchor_override(anchor)
        if validation["valid"]:
            canonical_key = normalize_anchor_name(anchor.get("canonical_name"))
            valid_anchors[canonical_key] = anchor
            for alias in anchor.get("aliases") or []:
                valid_anchors[normalize_anchor_name(alias)] = {
                    **anchor,
                    "_matched_alias": alias,
                }
            if validation["warnings"]:
                validation_warnings[key] = validation["warnings"]
        else:
            invalid_anchors[key] = {
                "anchor": anchor,
                "validation": validation,
            }

    return {
        "anchors": valid_anchors,
        "invalid_anchors": invalid_anchors,
        "validation_warnings": validation_warnings,
    }


def _anchor_result(
    raw_text: str,
    anchor_type: str,
    query_name: str,
    status: str,
    geometry: BaseGeometry | None = None,
    resolution_method: str | None = None,
    confidence: float = 0.0,
    source: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    longitude = None
    latitude = None
    geometry_type = None
    geometry_geojson = None
    if geometry is not None:
        geometry_type = geometry.geom_type
        geometry_geojson = mapping(geometry)
        if isinstance(geometry, Point):
            longitude = geometry.x
            latitude = geometry.y

    return {
        "raw_text": raw_text,
        "anchor_type": anchor_type,
        "query_name": query_name,
        "status": status,
        "geometry_type": geometry_type,
        "geometry": geometry_geojson,
        "longitude": longitude,
        "latitude": latitude,
        "resolution_method": resolution_method,
        "confidence": confidence,
        "source": source,
        "warnings": warnings or [],
    }


def _country_names(feature: dict[str, Any]) -> set[str]:
    props = feature.get("properties") or {}
    names = {
        props.get("NAME"),
        props.get("NAME_EN"),
        props.get("ADMIN"),
        props.get("NAME_LONG"),
        props.get("SOVEREIGNT"),
        props.get("name"),
    }
    return {normalize_name(str(name)) for name in names if name}


def find_country_feature(country_name: str, country_features: dict[str, Any]) -> dict[str, Any] | None:
    normalized = normalize_name(country_name)
    for feature in country_features.get("features") or []:
        if normalized in _country_names(feature):
            return feature
    return None


def _override_index(overrides: dict[str, Any] | None) -> dict[str, Any]:
    if not overrides:
        return {}
    if isinstance(overrides.get("anchors"), dict):
        return overrides["anchors"]
    return overrides


def resolve_manual_anchor(name: str, overrides: dict[str, Any] | None) -> dict[str, Any]:
    key = normalize_anchor_name(name)
    override = _override_index(overrides).get(key)
    if not override:
        return _anchor_result(
            raw_text=name,
            anchor_type="named_anchor",
            query_name=name,
            status="manual_required",
            resolution_method="manual_override_missing",
            confidence=0.0,
            source="anchor_overrides",
            warnings=["manual_anchor_missing"],
        )

    lon = override.get("longitude")
    lat = override.get("latitude")
    if lon is None or lat is None:
        return _anchor_result(
            raw_text=name,
            anchor_type=override.get("anchor_type", "named_anchor"),
            query_name=name,
            status="manual_required",
            resolution_method="manual_override_incomplete",
            confidence=0.0,
            source="anchor_overrides",
            warnings=["manual_anchor_missing_coordinates"],
        )

    method = "manual_override_alias" if override.get("_matched_alias") else "manual_override_exact"
    result = _anchor_result(
        raw_text=name,
        anchor_type=override.get("anchor_type", "named_anchor"),
        query_name=override.get("canonical_name", name),
        status="resolved",
        geometry=Point(float(lon), float(lat)),
        resolution_method=method,
        confidence=1.0,
        source=override.get("source_reference"),
        warnings=[],
    )
    result["manual_verified"] = True
    result["source_name"] = override.get("source_name")
    result["verified_at"] = override.get("verified_at")
    result["verified_by"] = override.get("verified_by")
    return result


def resolve_country_coastline(
    country_name: str,
    country_features: dict[str, Any],
    land_mask: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del land_mask
    feature = find_country_feature(country_name, country_features)
    if not feature:
        return _anchor_result(
            raw_text=country_name,
            anchor_type="country_coastline",
            query_name=country_name,
            status="unresolved",
            resolution_method="country_name_not_found",
            warnings=["missing_country_feature"],
        )

    geometry = shape(feature["geometry"]).boundary
    return _anchor_result(
        raw_text=country_name,
        anchor_type="country_coastline",
        query_name=country_name,
        status="ambiguous",
        geometry=geometry,
        resolution_method="country_polygon_boundary",
        confidence=0.4,
        source="country_features",
        warnings=["country_boundary_includes_land_borders_not_only_coastline"],
    )


def resolve_country_border(
    country_a: str,
    country_b: str,
    country_features: dict[str, Any],
) -> dict[str, Any]:
    feature_a = find_country_feature(country_a, country_features)
    feature_b = find_country_feature(country_b, country_features)
    if not feature_a or not feature_b:
        missing = country_a if not feature_a else country_b
        return _anchor_result(
            raw_text=f"{country_a}-{country_b} border",
            anchor_type="country_border",
            query_name=f"{country_a}-{country_b}",
            status="unresolved",
            resolution_method="country_name_not_found",
            warnings=[f"missing_country_feature:{missing}"],
        )

    border = shape(feature_a["geometry"]).boundary.intersection(shape(feature_b["geometry"]).boundary)
    if border.is_empty:
        return _anchor_result(
            raw_text=f"{country_a}-{country_b} border",
            anchor_type="country_border",
            query_name=f"{country_a}-{country_b}",
            status="unresolved",
            resolution_method="boundary_intersection_empty",
            warnings=["countries_do_not_share_detectable_boundary"],
        )

    return _anchor_result(
        raw_text=f"{country_a}-{country_b} border",
        anchor_type="country_border",
        query_name=f"{country_a}-{country_b}",
        status="ambiguous",
        geometry=border,
        resolution_method="country_boundary_intersection",
        confidence=0.6,
        source="country_features",
        warnings=["border_intersection_may_include_inland_segments"],
    )


def resolve_coastal_border_anchor(
    country_a: str,
    country_b: str,
    country_features: dict[str, Any],
    land_mask: dict[str, Any] | None = None,
) -> dict[str, Any]:
    border_result = resolve_country_border(country_a, country_b, country_features)
    if border_result["status"] != "ambiguous" or not land_mask:
        border_result["status"] = "manual_required" if border_result["status"] == "ambiguous" else border_result["status"]
        border_result["warnings"].append("coastal_endpoint_requires_land_mask_disambiguation")
        return border_result

    # The current land mask has no country attribution. It can show that a point is near land,
    # but it cannot prove which shared-border endpoint is the coastal endpoint.
    border_result["status"] = "manual_required"
    border_result["warnings"].append("land_mask_has_no_country_attribution_for_unique_coastal_endpoint")
    return border_result


def _candidate_country_names(country_features: dict[str, Any]) -> list[str]:
    names = []
    for feature in country_features.get("features") or []:
        props = feature.get("properties") or {}
        name = props.get("NAME_EN") or props.get("NAME") or props.get("ADMIN") or props.get("name")
        if name:
            names.append(str(name))
    return sorted(set(names), key=len, reverse=True)


def resolve_boundary_anchors(
    anchor_conditions: list[dict[str, Any]],
    country_features: dict[str, Any],
    overrides: dict[str, Any] | None = None,
    land_mask: dict[str, Any] | None = None,
) -> dict[str, Any]:
    anchors = []
    for condition in anchor_conditions:
        condition_type = condition.get("type")
        if condition_type == "country_coastline":
            anchors.append(
                resolve_country_coastline(
                    condition.get("country") or condition.get("query_name") or "",
                    country_features,
                    land_mask,
                )
            )
        elif condition_type == "country_border":
            anchors.append(
                resolve_coastal_border_anchor(
                    condition.get("country_a") or "",
                    condition.get("country_b") or "",
                    country_features,
                    land_mask,
                )
            )
        elif condition_type == "named_anchor":
            anchors.append(resolve_manual_anchor(condition.get("name") or "", overrides))
        else:
            anchors.append(
                _anchor_result(
                    raw_text=condition.get("raw", ""),
                    anchor_type=condition_type or "unknown",
                    query_name=condition.get("name") or "",
                    status="unresolved",
                    resolution_method="unsupported_anchor_condition",
                    warnings=["unsupported_anchor_condition"],
                )
            )

    counts = {
        "resolved_count": sum(1 for anchor in anchors if anchor["status"] == "resolved"),
        "ambiguous_count": sum(1 for anchor in anchors if anchor["status"] == "ambiguous"),
        "manual_required_count": sum(1 for anchor in anchors if anchor["status"] == "manual_required"),
        "unresolved_count": sum(1 for anchor in anchors if anchor["status"] == "unresolved"),
    }
    return {
        "anchors": anchors,
        **counts,
        "needs_review": any(anchor["status"] != "resolved" for anchor in anchors),
    }


def collect_pending_anchors(zone_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collect anchors that still need manual or GIS resolution."""
    pending = []
    for zone_result in zone_results:
        zone_name = zone_result.get("zone_name")
        for anchor in zone_result.get("anchor_statuses") or []:
            if anchor.get("status") == "resolved":
                continue
            pending.append(
                {
                    "zone_name": zone_name,
                    "anchor_name": anchor.get("query_name"),
                    "anchor_type": anchor.get("anchor_type"),
                    "status": anchor.get("status"),
                    "raw_text": anchor.get("raw_text"),
                    "reason": ", ".join(anchor.get("warnings") or []),
                }
            )
    return pending


COUNTRY_BORDER_PATTERN = re.compile(r"\b([A-Z][A-Za-z]+)-([A-Z][A-Za-z]+) border\b")
COAST_OF_PATTERN = re.compile(r"\bcoast of ([A-Z][A-Za-z ]+)")
COASTLINE_PATTERN = re.compile(r"\b([A-Z][A-Za-z ]+) coastline\b")
BAY_ANCHOR_PATTERN = re.compile(r"\b([A-ZÀ-ÿ][A-Za-zÀ-ÿ' ]+?\sBay|Baía\s+[A-Za-zÀ-ÿ' ]+)\b")
CAPE_PENINSULA_PATTERN = re.compile(r"\b(Cape\s+[A-ZÀ-ÿ][A-Za-zÀ-ÿ' ]+?\sPeninsula)\b")
CAPE_ANCHOR_PATTERN = re.compile(r"\b(Cape\s+[A-ZÀ-ÿ][A-Za-zÀ-ÿ' ]+)\b")
PENINSULA_ANCHOR_PATTERN = re.compile(r"\b([A-ZÀ-ÿ][A-Za-zÀ-ÿ' ]+?\sPeninsula)\b")


def detect_anchor_conditions(text: str, country_features: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Detect conservative anchor conditions from one boundary text line."""
    conditions = []
    for match in COUNTRY_BORDER_PATTERN.finditer(text):
        conditions.append(
            {
                "type": "country_border",
                "country_a": match.group(1).strip(),
                "country_b": match.group(2).strip(),
                "raw": match.group(0),
            }
        )
    for match in COAST_OF_PATTERN.finditer(text):
        conditions.append(
            {
                "type": "country_coastline",
                "country": match.group(1).strip(),
                "raw": match.group(0),
            }
        )
    for match in COASTLINE_PATTERN.finditer(text):
        conditions.append(
            {
                "type": "country_coastline",
                "country": match.group(1).strip(),
                "raw": match.group(0),
            }
        )
    occupied_spans = []

    def add_named_anchor(match, anchor_type: str):
        name = re.sub(r"\s+at$", "", match.group(1).strip())
        span = match.span(1)
        if any(not (span[1] <= used[0] or span[0] >= used[1]) for used in occupied_spans):
            return
        occupied_spans.append(span)
        conditions.append(
            {
                "type": "named_anchor",
                "name": name,
                "anchor_type": anchor_type,
                "raw": name,
            }
        )

    for match in CAPE_PENINSULA_PATTERN.finditer(text):
        add_named_anchor(match, "peninsula")
    for match in BAY_ANCHOR_PATTERN.finditer(text):
        add_named_anchor(match, "bay")
    for match in CAPE_ANCHOR_PATTERN.finditer(text):
        add_named_anchor(match, "cape")
    for match in PENINSULA_ANCHOR_PATTERN.finditer(text):
        add_named_anchor(match, "peninsula")

    if country_features:
        names = _candidate_country_names(country_features)
        lowered_text = text.lower()
        for name in names:
            if f"{name.lower()} border" in lowered_text and not any(
                condition.get("country") == name or condition.get("country_a") == name
                for condition in conditions
            ):
                conditions.append(
                    {
                        "type": "country_coastline",
                        "country": name,
                        "raw": f"{name} border",
                    }
                )

    return conditions

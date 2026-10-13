"""Read-only arrival board for the six humidity pilot ports.

Only confirmed insurance declarations are included. An ETA entered on a
declaration is not an AIS-derived prediction, so the API labels it explicitly.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from risk_monitor.supabase_client import supabase


SHANGHAI = ZoneInfo("Asia/Shanghai")
PAGE_SIZE = 500
CONFIRMED_STATUSES = {"confirmed", "covered"}
PORT_ALIASES = {
    "CN_YINGKOU": {"YINGKOU", "营口", "营口港"},
    "CN_TIANJIN": {"TIANJIN", "天津", "天津港"},
    "CN_QINGDAO": {"QINGDAO", "CNQDG", "青岛", "青岛港"},
    "CN_LIANYUNGANG": {"LIANYUNGANG", "CNLYG", "连云港", "连云港港"},
    "CN_ZHANJIANG": {"ZHANJIANG", "湛江", "湛江港"},
    "CN_FANGCHENGGANG": {"FANGCHENGGANG", "防城港", "防城港港"},
}


def _port_key(value: str | None) -> str:
    return re.sub(r"[\W_]+", "", unicodedata.normalize('NFKC', value or '').upper(), flags=re.UNICODE)


def match_destination_ports(value: str | None) -> frozenset[str]:
    """Exact aliases per explicitly delimited discharge-port fragment, never prose search.

    Returns runtime-derived pilot codes without modifying the declaration text.
    Spaces inside a name are normalized, not treated as port separators.
    """
    fragments = {_port_key(fragment) for fragment in re.split(r'[、，,；;|｜]', value or '')}
    fragments.discard('')
    return frozenset(code for code, aliases in PORT_ALIASES.items()
                     if fragments.intersection({_port_key(alias) for alias in aliases | {code}}))


def _parse_time(value: str | datetime | None) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None


def _batches(values: list[str]):
    for index in range(0, len(values), PAGE_SIZE):
        yield values[index:index + PAGE_SIZE]


class PortArrivalRepository:
    def list_eta_shipments(self, start: datetime, end: datetime) -> list[dict]:
        rows: list[dict] = []
        offset = 0
        while True:
            page = (
                supabase.table("insurance_shipments")
                .select("id,declaration_id,vessel_name,imo_number,discharge_port,eta,updated_at")
                .gte("eta", start.isoformat())
                .lt("eta", end.isoformat())
                .order("eta")
                .range(offset, offset + PAGE_SIZE - 1)
                .execute()
            ).data or []
            rows.extend(page)
            if len(page) < PAGE_SIZE:
                return rows
            offset += PAGE_SIZE

    def get_declarations(self, ids: list[str]) -> list[dict]:
        rows: list[dict] = []
        for batch in _batches(ids):
            rows.extend((supabase.table("insurance_declarations")
                         .select("id,status,policy_id").in_("id", batch).execute()).data or [])
        return rows

    def get_policies(self, ids: list[str]) -> list[dict]:
        rows: list[dict] = []
        for batch in _batches(ids):
            rows.extend((supabase.table("insurance_policies")
                         .select("id,status").in_("id", batch).execute()).data or [])
        return rows


def get_port_arrivals(
    port_code: str,
    *,
    repository: PortArrivalRepository | None = None,
    now: datetime | None = None,
) -> dict:
    if port_code not in PORT_ALIASES:
        raise ValueError("Unknown humidity pilot port")
    repository = repository or PortArrivalRepository()
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")
    now = now.astimezone(timezone.utc)
    local_today = now.astimezone(SHANGHAI).date()
    # Today plus the next five complete local calendar dates; end is exclusive.
    end = datetime.combine(local_today + timedelta(days=6), datetime.min.time(), SHANGHAI).astimezone(timezone.utc)
    shipments = [row for row in repository.list_eta_shipments(now, end)
                 if port_code in match_destination_ports(row.get("discharge_port"))]

    declaration_ids = sorted({str(row["declaration_id"]) for row in shipments if row.get("declaration_id")})
    declarations = {str(row["id"]): row for row in repository.get_declarations(declaration_ids)} if declaration_ids else {}
    policy_ids = sorted({str(row["policy_id"]) for row in declarations.values()
                         if row.get("status") in CONFIRMED_STATUSES and row.get("policy_id")})
    policies = {str(row["id"]): row for row in repository.get_policies(policy_ids)} if policy_ids else {}

    arrivals_by_vessel: dict[str, tuple[datetime, dict]] = {}
    for shipment in shipments:
        declaration = declarations.get(str(shipment.get("declaration_id")))
        if not declaration or declaration.get("status") not in CONFIRMED_STATUSES:
            continue
        policy = policies.get(str(declaration.get("policy_id")))
        if not policy or policy.get("status") == "cancelled":
            continue
        eta = _parse_time(shipment.get("eta"))
        if eta is None or not now <= eta < end:
            continue
        name = str(shipment.get("vessel_name") or "").strip()
        imo = str(shipment.get("imo_number") or "").strip() or None
        if not name and not imo:
            continue
        vessel_key = imo or _port_key(name)
        updated = _parse_time(shipment.get("updated_at")) or eta
        arrival = {"vessel_name": name or f"IMO {imo}", "imo_number": imo,
                   "eta": eta.isoformat(), "eta_source": "insurance_declaration",
                   "eta_scope": "declaration_voyage",
                   "declaration_id": str(shipment['declaration_id']), "shipment_id": str(shipment['id']),
                   "discharge_port": shipment.get('discharge_port'),
                   "matched_port_codes": sorted(match_destination_ports(shipment.get('discharge_port')))}
        if vessel_key not in arrivals_by_vessel or updated > arrivals_by_vessel[vessel_key][0]:
            arrivals_by_vessel[vessel_key] = (updated, arrival)

    arrivals = sorted((item for _, item in arrivals_by_vessel.values()),
                      key=lambda item: (item["eta"], item["vessel_name"]))
    return {"port_code": port_code, "timezone": "Asia/Shanghai",
            "window_start": now.isoformat(), "window_end": end.isoformat(),
            "eta_source": "insurance_declaration", "arrivals": arrivals}

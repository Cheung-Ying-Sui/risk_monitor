"""MVP inference: a covered voyage ends when its vessel sails after berthing.

This is an operational assumption, not evidence that cargo was discharged or a
determination of the policy's legal termination date. Unknown ports fail closed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Any

from risk_monitor.navigation.port_reference import iter_ports


BERTH_RADIUS_KM = 30.0
DEPARTURE_RADIUS_KM = 80.0
MIN_BERTH_MINUTES = 10
MAX_POSITION_AGE = timedelta(hours=2)
ENDED_STATUS = "ended_by_mvp_departure"

# Approximate port reference points, not berth polygons. These aliases must be
# exact; broad phrases such as "China main ports" must never close a voyage.
PILOT_PORTS = (
    ("Yingkou", 40.3, 122.083333, ("营口", "营口港", "YINGKOU")),
    ("Tianjin", 38.966667, 117.833333, ("天津", "天津港", "TIANJIN")),
    ("Qingdao", 36.033333, 120.266667, ("青岛", "青岛港", "QINGDAO", "CNQDG")),
    ("Lianyungang", 34.75, 119.45, ("连云港", "连云港港", "LIANYUNGANG", "CNLYG")),
    ("Zhanjiang", 21.2, 110.4, ("湛江", "湛江港", "ZHANJIANG")),
    ("Fangchenggang", 21.60682, 108.35155, ("防城港", "防城港港", "FANGCHENGGANG")),
)


def _key(value: Any) -> str:
    return "".join(character for character in str(value or "").upper() if character.isalnum())


def _time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None


def _port(value: str | None) -> dict[str, Any] | None:
    name = _key(value)
    if not name:
        return None
    for label, latitude, longitude, aliases in PILOT_PORTS:
        if name in {_key(alias) for alias in aliases}:
            return {"name": label, "latitude": latitude, "longitude": longitude}
    for port in iter_ports():
        if name in {_key(alias) for alias in (port["unlocode"], port["port_name"], *port["aliases"])}:
            return {"name": port["port_name"], "latitude": port["latitude"], "longitude": port["longitude"]}
    return None


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    a = sin(radians(lat2 - lat1) / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(radians(lon2 - lon1) / 2) ** 2
    return 12742 * asin(sqrt(a))


def next_lifecycle(shipment: dict[str, Any], position: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any] | None:
    """Return a new lifecycle snapshot, or None if no eligible transition."""
    port = _port(shipment.get("discharge_port"))
    observed = _time(position.get("observed_at"))
    now = now or datetime.now(timezone.utc)
    if not port or not observed or now.tzinfo is None or observed > now + timedelta(minutes=5) or now - observed > MAX_POSITION_AGE:
        return None
    if _time(shipment.get("etd")) and observed < _time(shipment["etd"]):
        return None
    previous = (shipment.get("extra_data") or {}).get("voyage_lifecycle") or {}
    if previous.get("state") == "ended" or (shipment.get("coverage_status") == ENDED_STATUS):
        return None
    last = _time(previous.get("last_observed_at"))
    if last and observed <= last:
        return None
    try:
        latitude = float(position["latitude"])
        longitude = float(position["longitude"])
        speed = float(position["sog"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180 and 0 <= speed <= 80):
        return None
    distance = _distance_km(latitude, longitude, port["latitude"], port["longitude"])
    nav = _key(position.get("nav_status"))
    moored = nav in {"MOORED", "MOORED5", "5", "BERTHED", "ALONGSIDE"} and speed <= 1
    moving = speed >= 2
    state = previous.get("state")
    snapshot = {**previous, "port": port["name"], "last_observed_at": observed.isoformat(), "last_position_id": position.get("position_id"), "rule": "mvp_berth_then_departure"}
    if moored and distance <= BERTH_RADIUS_KM:
        if state == "berthed":
            return snapshot
        first = _time(previous.get("first_berth_observed_at"))
        if state == "berth_candidate" and first and observed - first >= timedelta(minutes=MIN_BERTH_MINUTES):
            return {**snapshot, "state": "berthed", "berth_confirmed_at": observed.isoformat()}
        if state != "berth_candidate":
            return {**snapshot, "state": "berth_candidate", "first_berth_observed_at": observed.isoformat()}
        return snapshot
    if state == "berthed" and moving and distance <= DEPARTURE_RADIUS_KM:
        return {**snapshot, "state": "ended", "ended_at": observed.isoformat(), "departure_sog": speed, "departure_latitude": latitude, "departure_longitude": longitude}
    # A temporary AIS state/speed mismatch does not erase an established berth.
    return None


class VoyageLifecycleGateway:
    def list_ended_imos(self) -> list[str]:
        from risk_monitor.supabase_client import supabase
        imos: set[str] = set()
        offset = 0
        while True:
            page = (supabase.table("insurance_shipments").select("imo_number")
                    .eq("coverage_status", ENDED_STATUS)
                    .range(offset, offset + 499).execute()).data or []
            imos.update(str(row["imo_number"]) for row in page if row.get("imo_number"))
            if len(page) < 500:
                return sorted(imos)
            offset += 500

    def list_shipments(self, imo: str) -> list[dict[str, Any]]:
        from risk_monitor.supabase_client import supabase

        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = (supabase.table("insurance_shipments")
                    .select("id,declaration_id,imo_number,discharge_port,etd,coverage_status,extra_data,updated_at")
                    .eq("imo_number", imo).range(offset, offset + 499).execute()).data or []
            rows.extend(page)
            if len(page) < 500:
                return rows
            offset += 500

    def list_declarations(self, ids: list[str]) -> list[dict[str, Any]]:
        from risk_monitor.supabase_client import supabase
        if not ids:
            return []
        return (supabase.table("insurance_declarations")
                .select("id,policy_id,status").in_("id", ids).execute()).data or []

    def list_policies(self, ids: list[str]) -> list[dict[str, Any]]:
        from risk_monitor.supabase_client import supabase
        if not ids:
            return []
        return (supabase.table("insurance_policies")
                .select("id,status").in_("id", ids).execute()).data or []

    def save_transition(self, shipment: dict[str, Any], lifecycle: dict[str, Any]) -> bool:
        from risk_monitor.supabase_client import supabase
        extra = {**(shipment.get("extra_data") or {}), "voyage_lifecycle": lifecycle}
        payload: dict[str, Any] = {"extra_data": extra}
        if lifecycle["state"] == "ended":
            payload["coverage_status"] = ENDED_STATUS
        query = (supabase.table("insurance_shipments").update(payload)
                 .eq("id", shipment["id"]).eq("updated_at", shipment["updated_at"]))
        return bool(query.execute().data)

    def complete_declaration(self, declaration_id: str) -> None:
        from risk_monitor.supabase_client import supabase
        result = (supabase.table("insurance_declarations").update({"status": "completed"})
                  .eq("id", declaration_id).in_("status", ["confirmed", "covered"]).execute())
        if not result.data:
            raise RuntimeError(f"Declaration {declaration_id} was not completed")

    def stop_insurance_tracking(self, imo: str) -> bool:
        from risk_monitor.tracking_repository import deactivate_tracking_by_vessel_id, get_tracking_status_by_vessel_id
        from risk_monitor.vessel_query_repository import get_vessel_by_imo

        vessel = get_vessel_by_imo(imo)
        if not vessel:
            return False
        tracking = get_tracking_status_by_vessel_id(vessel["id"])
        # A separate high-risk or manual tracking mode must not be stopped.
        if not tracking or not tracking.get("is_active") or tracking.get("tracking_mode") != "history_tracking":
            return False
        deactivate_tracking_by_vessel_id(vessel["id"])
        return True


class VoyageLifecycleService:
    def __init__(self, gateway: VoyageLifecycleGateway | None = None):
        self.gateway = gateway or VoyageLifecycleGateway()

    def reconcile_finished(self) -> None:
        for imo in self.gateway.list_ended_imos():
            self.process_position(imo, {})

    def process_position(self, imo: str, position: dict[str, Any], *, now: datetime | None = None) -> list[str]:
        if not (str(imo or "").isdigit() and len(str(imo)) == 7):
            return []
        shipments = self.gateway.list_shipments(str(imo))
        declarations = {row["id"]: row for row in self.gateway.list_declarations(
            sorted({row["declaration_id"] for row in shipments}))}
        policies = {row["id"]: row for row in self.gateway.list_policies(
            sorted({row["policy_id"] for row in declarations.values()}))}
        changed: list[str] = []
        for shipment in shipments:
            declaration = declarations.get(shipment["declaration_id"])
            if not declaration or declaration["status"] not in {"confirmed", "covered"}:
                continue
            policy = policies.get(declaration["policy_id"])
            if not policy or policy["status"] == "cancelled":
                continue
            lifecycle = next_lifecycle(shipment, position, now=now)
            if lifecycle is None or not self.gateway.save_transition(shipment, lifecycle):
                continue
            shipment["extra_data"] = {**(shipment.get("extra_data") or {}), "voyage_lifecycle": lifecycle}
            if lifecycle["state"] == "ended":
                shipment["coverage_status"] = ENDED_STATUS
                changed.append(shipment["id"])

        for declaration_id, declaration in declarations.items():
            if declaration["status"] in {"confirmed", "covered"} and all(
                row.get("coverage_status") == ENDED_STATUS for row in shipments if row["declaration_id"] == declaration_id
            ):
                self.gateway.complete_declaration(declaration_id)
                declarations[declaration_id]["status"] = "completed"

        remaining = any(
            row.get("coverage_status") != ENDED_STATUS
            and declarations.get(row["declaration_id"], {}).get("status") in {"confirmed", "covered"}
            and policies.get(declarations[row["declaration_id"]]["policy_id"], {}).get("status") != "cancelled"
            for row in shipments
        )
        owned = any((row.get("extra_data") or {}).get("insurance_tracking_owned") is True for row in shipments)
        if any(row.get("coverage_status") == ENDED_STATUS for row in shipments) and not remaining and owned:
            self.gateway.stop_insurance_tracking(str(imo))
        return changed

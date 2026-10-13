"""Best-effort link from confirmed insurance IMO to the existing AIS tracker."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from risk_monitor import datalastic_client, deepseek_mmsi_resolver
from risk_monitor.external_vessel_adapter import normalize_chinaports_vessel, normalize_latest_position


logger = logging.getLogger(__name__)
_IMO = re.compile(r"^\d{7}$")


class InsuranceTrackingGateway:
    def get_vessel_by_imo(self, imo: str) -> dict[str, Any] | None:
        from risk_monitor.vessel_query_repository import get_vessel_by_imo
        return get_vessel_by_imo(imo)

    def get_vessel_by_mmsi(self, mmsi: str) -> dict[str, Any] | None:
        from risk_monitor.vessel_query_repository import get_vessel_by_mmsi
        return get_vessel_by_mmsi(mmsi)

    def get_tracking_status(self, vessel_id: str) -> dict[str, Any] | None:
        from risk_monitor.tracking_repository import get_tracking_status_by_vessel_id
        return get_tracking_status_by_vessel_id(vessel_id)

    def get_latest_position(self, vessel_id: str) -> dict[str, Any] | None:
        from risk_monitor.latest_position_repository import get_latest_position_by_vessel_id
        return get_latest_position_by_vessel_id(vessel_id)

    def activate(self, vessel: dict[str, Any]) -> dict[str, Any]:
        from risk_monitor.tracking_repository import activate_tracking_by_vessel
        return activate_tracking_by_vessel(vessel)

    def fetch_by_imo(self, imo: str) -> dict[str, Any]:
        return datalastic_client.fetch_vessel_by_imo(imo)

    def suggest_mmsi(self, imo: str, vessel_name: str | None) -> dict[str, str] | None:
        return deepseek_mmsi_resolver.suggest_mmsi(imo, vessel_name)

    def fetch_by_mmsi(self, mmsi: str) -> dict[str, Any]:
        from risk_monitor.chinaports_client import fetch_ship_info
        return fetch_ship_info(mmsi)

    def fetch_chinaports_by_imo(self, imo: str) -> dict[str, Any]:
        from risk_monitor.chinaports_client import fetch_ship_info
        return fetch_ship_info(imo=imo)

    def onboard(self, candidate: dict[str, Any]) -> dict[str, Any]:
        from risk_monitor.vessel_search_service import VesselSearchService
        return VesselSearchService().onboard(candidate)

    def mark_insurance_tracking_owned(self, shipment: dict[str, Any]) -> None:
        from risk_monitor.supabase_client import supabase
        if not shipment.get("id"):
            return
        extra = {**(shipment.get("extra_data") or {}), "insurance_tracking_owned": True}
        (supabase.table("insurance_shipments").update({"extra_data": extra})
         .eq("id", shipment["id"]).execute())

    def save_position(self, vessel_id: str, mmsi: str, position: dict[str, Any]) -> None:
        from risk_monitor.position_repository import upsert_position_for_vessel
        upsert_position_for_vessel(vessel_id, mmsi, position, source_code="DATALASTIC")

    def refresh_insurance_prediction(self, vessel_id: str, mmsi: str) -> None:
        from risk_monitor.navigation.prediction_trigger import refresh_prediction_after_position
        refresh_prediction_after_position(vessel_id=vessel_id, mmsi=mmsi)


class MmsiVerificationError(ValueError):
    """A human-confirmed MMSI could not be matched to the declaration IMO."""


class MmsiSourceUnavailableError(RuntimeError):
    """The AIS identity source was unavailable during confirmation."""


class InsuranceTrackingService:
    def __init__(
        self,
        gateway: InsuranceTrackingGateway | None = None,
        provider_configured: bool | None = None,
        candidate_configured: bool | None = None,
    ):
        self.gateway = gateway or InsuranceTrackingGateway()
        self.provider_configured = datalastic_client.is_configured() if provider_configured is None else provider_configured
        self.candidate_configured = deepseek_mmsi_resolver.is_configured() if candidate_configured is None else candidate_configured

    def sync_imo(self, imo: str | None, vessel_name: str | None = None, confirmed_mmsi: str | None = None) -> str:
        identifier = str(imo or "").strip()
        if not _IMO.fullmatch(identifier):
            return "invalid_imo"

        if confirmed_mmsi:
            return self._sync_with_confirmed_mmsi(identifier, str(confirmed_mmsi).strip())

        vessel = self.gateway.get_vessel_by_imo(identifier)
        if vessel and vessel.get("mmsi"):
            self.gateway.activate(vessel)
            if self.provider_configured:
                data = self.gateway.fetch_by_imo(identifier)
                if str(data.get("imo") or "").strip() != identifier or str(data.get("mmsi") or "").strip() != str(vessel["mmsi"]):
                    return "identity_conflict"
                return "tracking" if self._save_provider_position(vessel["id"], vessel["mmsi"], data) else "awaiting_position"
            return "tracking"
        if not self.provider_configured:
            if vessel:
                return "identity_conflict"
            return "mmsi_confirmation_required" if self.candidate_configured else "ais_provider_not_configured"

        data = self.gateway.fetch_by_imo(identifier)
        if str(data.get("imo") or "").strip() != identifier:
            return "imo_mismatch"
        mmsi = str(data.get("mmsi") or "").strip()
        if not re.fullmatch(r"\d{9}", mmsi):
            return "mmsi_unavailable"
        if vessel:
            # A pre-existing IMO row without MMSI needs explicit identity repair.
            return "identity_conflict"

        candidate = {
            "source": "datalastic",
            "imo": identifier,
            "mmsi": mmsi,
            "name": data.get("name"),
            "ship_type": data.get("type"),
            "flag_state": data.get("country_iso"),
        }
        onboarded = self.gateway.onboard(candidate)
        if not onboarded.get("is_tracked"):
            return "activation_failed"
        if onboarded.get("id"):
            return "tracking" if self._save_provider_position(str(onboarded["id"]), mmsi, data) else "awaiting_position"
        return "awaiting_position"

    def suggest_mmsi(self, imo: str, vessel_name: str | None = None) -> dict[str, str] | None:
        if not _IMO.fullmatch(str(imo or "").strip()):
            raise MmsiVerificationError("请先填写有效的 7 位 IMO。")
        return self.gateway.suggest_mmsi(imo, vessel_name)

    def verify_confirmed_mmsi(self, imo: str, mmsi: str) -> dict[str, Any]:
        if not _IMO.fullmatch(str(imo or "").strip()) or not re.fullmatch(r"\d{9}", str(mmsi or "").strip()):
            raise MmsiVerificationError("核实需要 7 位 IMO 和 9 位 MMSI。")
        try:
            raw = self.gateway.fetch_by_mmsi(mmsi)
        except Exception as exc:
            raise MmsiSourceUnavailableError("Chinaports 暂时无法核实船舶身份，请稍后重试。") from exc
        verified = normalize_chinaports_vessel(raw)
        if not verified or verified.get("imo") != imo or verified.get("mmsi") != mmsi:
            raise MmsiVerificationError("该 MMSI 与申报 IMO 不匹配，请检查并更正号码。")
        return verified

    def validate_confirmed_shipments(self, shipments: list[dict[str, Any]]) -> None:
        for shipment in shipments:
            extra = shipment.get("extra_data") or {}
            if extra.get("mmsi_confirmed") is not True:
                continue
            self.verify_confirmed_mmsi(
                str(shipment.get("imo_number") or "").strip(),
                str(extra.get("mmsi_candidate") or "").strip(),
            )

    def _sync_with_confirmed_mmsi(self, imo: str, mmsi: str) -> str:
        try:
            verified = self.verify_confirmed_mmsi(imo, mmsi)
        except MmsiSourceUnavailableError:
            return "verification_source_unavailable"
        except MmsiVerificationError:
            return "mmsi_unverified"
        vessel = self.gateway.get_vessel_by_imo(imo)
        if vessel and vessel.get("mmsi") and str(vessel["mmsi"]) != mmsi:
            return "identity_conflict"
        if vessel and not vessel.get("mmsi"):
            return "identity_conflict"
        onboarded = self.gateway.onboard(verified)
        if not onboarded.get("is_tracked"):
            return "activation_failed"
        if onboarded.get("warnings"):
            logger.warning("insurance_ais_onboard_warnings imo=%s warnings=%s", imo, onboarded["warnings"])
            return "awaiting_position"
        return "tracking" if onboarded.get("latest_position") else "awaiting_position"

    def _save_provider_position(self, vessel_id: str, mmsi: str, data: dict[str, Any]) -> bool:
        position = normalize_latest_position({
            "lat": data.get("lat"), "lon": data.get("lon"),
            "sog": data.get("speed"), "cog": data.get("course"),
            "heading": data.get("heading"),
            "navigation_status": data.get("navigational_status"),
            "destination": data.get("destination"),
            "observed_at": data.get("last_position_UTC"),
        })
        if position:
            self.gateway.save_position(str(vessel_id), str(mmsi), position)
            return True
        return False

    def sync_shipments(self, shipments: list[dict[str, Any]]) -> None:
        seen: set[str] = set()
        for shipment in shipments:
            imo = str(shipment.get("imo_number") or "").strip()
            if not _IMO.fullmatch(imo) or imo in seen:
                continue
            seen.add(imo)
            try:
                raw = self.gateway.fetch_chinaports_by_imo(imo)
                candidate = normalize_chinaports_vessel(raw)
                if not candidate or candidate.get("imo") != imo:
                    result = "identity_conflict"
                else:
                    existing = self.gateway.get_vessel_by_mmsi(candidate["mmsi"])
                    tracking = self.gateway.get_tracking_status(str(existing["id"])) if existing else None
                    insurance_activated = not tracking or not tracking.get("is_active")
                    onboarded = self.gateway.onboard({**candidate, "source": "chinaports"})
                    result = "tracking" if onboarded.get("is_tracked") else "activation_failed"
                    if result == "tracking" and insurance_activated:
                        for owned_shipment in shipments:
                            if str(owned_shipment.get("imo_number") or "").strip() == imo and owned_shipment.get("id"):
                                self.gateway.mark_insurance_tracking_owned(owned_shipment)
                    if result == "tracking" and onboarded.get('id'):
                        # Also refresh when onboarding reused an existing AIS record.
                        self.gateway.refresh_insurance_prediction(str(onboarded['id']), candidate['mmsi'])
                logger.info("insurance_ais_sync imo=%s result=%s", imo, result)
            except Exception:
                logger.exception("insurance_ais_sync_failed imo=%s", imo)

    def status_for(self, imo: str | None, confirmed_mmsi: str | None = None) -> str:
        identifier = str(imo or "").strip()
        if not _IMO.fullmatch(identifier):
            return "invalid_imo"
        vessel = self.gateway.get_vessel_by_imo(identifier)
        if not vessel or not vessel.get("mmsi"):
            return "awaiting_imo_match"
        tracking = self.gateway.get_tracking_status(str(vessel["id"]))
        if not tracking or not tracking.get("is_active"):
            return "not_tracking"
        position = self.gateway.get_latest_position(str(vessel["id"]))
        if not position or not position.get("observed_at"):
            return "awaiting_position"
        try:
            observed_at = datetime.fromisoformat(str(position["observed_at"]).replace("Z", "+00:00"))
            if observed_at.tzinfo is None:
                observed_at = observed_at.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - observed_at
            return "current" if -timedelta(minutes=5) <= age <= timedelta(hours=24) else "stale_position"
        except ValueError:
            return "stale_position"

from typing import Any

from risk_monitor.external_vessel_adapter import (
    EXTERNAL_SOURCE_CHINAPORTS,
    normalize_chinaports_vessel,
    normalize_imo,
    normalize_mmsi,
    normalize_onboard_candidate,
)


class VesselNotFoundError(Exception):
    pass


class ExternalSearchUnsupportedError(Exception):
    pass


class ExternalSourceUnavailableError(Exception):
    pass


class VesselConflictError(Exception):
    pass


class VesselValidationError(Exception):
    pass


class VesselSearchGateway:
    def get_vessel_by_mmsi(self, mmsi: str) -> dict[str, Any] | None:
        from risk_monitor.vessel_query_repository import get_vessel_by_mmsi

        return get_vessel_by_mmsi(mmsi)

    def get_vessel_by_imo(self, imo: str) -> dict[str, Any] | None:
        from risk_monitor.vessel_query_repository import get_vessel_by_imo

        return get_vessel_by_imo(imo)

    def get_latest_position_by_vessel_id(
        self,
        vessel_id: str,
    ) -> dict[str, Any] | None:
        from risk_monitor.latest_position_repository import (
            get_latest_position_by_vessel_id,
        )

        return get_latest_position_by_vessel_id(vessel_id)

    def get_tracking_status_by_vessel_id(
        self,
        vessel_id: str,
    ) -> dict[str, Any] | None:
        from risk_monitor.tracking_repository import get_tracking_status_by_vessel_id

        return get_tracking_status_by_vessel_id(vessel_id)

    def fetch_external_ship_info(self, mmsi: str) -> dict[str, Any]:
        from risk_monitor.chinaports_client import (
            ChinaportsClientError,
            fetch_ship_info,
        )

        try:
            return fetch_ship_info(mmsi)
        except ChinaportsClientError as exc:
            raise ExternalSourceUnavailableError(
                "External vessel source unavailable."
            ) from exc

    def upsert_vessel(self, vessel_data: dict[str, Any]) -> list[dict[str, Any]]:
        from risk_monitor.vessel_repository import upsert_vessel

        return upsert_vessel(vessel_data)

    def activate_tracking_by_vessel(
        self,
        vessel: dict[str, Any],
    ) -> dict[str, Any]:
        from risk_monitor.tracking_repository import activate_tracking_by_vessel

        return activate_tracking_by_vessel(vessel)

    def upsert_position_for_vessel(
        self,
        vessel_id: str,
        mmsi: str,
        position_data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        from risk_monitor.position_repository import upsert_position_for_vessel

        return upsert_position_for_vessel(
            vessel_id=vessel_id,
            mmsi=mmsi,
            position_data=position_data,
        )


class VesselSearchService:
    def __init__(self, gateway: VesselSearchGateway | None = None):
        self.gateway = gateway or VesselSearchGateway()

    def search(self, mmsi: str | None = None, imo: str | None = None):
        normalized_mmsi = normalize_mmsi(mmsi)
        normalized_imo = normalize_imo(imo)

        if not normalized_mmsi and not normalized_imo:
            raise VesselValidationError("Either imo or mmsi is required.")

        local_vessel = None
        if normalized_imo:
            local_vessel = self.gateway.get_vessel_by_imo(normalized_imo)
        elif normalized_mmsi:
            local_vessel = self.gateway.get_vessel_by_mmsi(normalized_mmsi)

        if local_vessel:
            if normalized_mmsi and str(local_vessel.get("mmsi")) != normalized_mmsi:
                raise VesselConflictError("IMO and MMSI identify different vessels.")
            return self._build_local_response(local_vessel)

        raw_external_vessel = self.gateway.fetch_external_ship_info(normalized_imo or normalized_mmsi)
        external_candidate = normalize_chinaports_vessel(raw_external_vessel)
        if not external_candidate:
            raise VesselNotFoundError("Vessel not found.")
        if ((normalized_imo and external_candidate.get("imo") != normalized_imo)
                or (normalized_mmsi and external_candidate.get("mmsi") != normalized_mmsi)):
            raise VesselConflictError("Chinaports returned a different vessel identity.")

        return external_candidate

    def onboard(self, candidate_data: dict[str, Any]) -> dict[str, Any]:
        candidate = normalize_onboard_candidate(candidate_data)
        mmsi = candidate.get("mmsi")
        if not mmsi:
            raise VesselValidationError("mmsi is required.")

        warnings: list[str] = []
        if candidate_data.get("latest_position") and not candidate.get(
            "latest_position"
        ):
            warnings.append("Latest position is invalid and was not persisted.")

        existing_vessel = self.gateway.get_vessel_by_mmsi(mmsi)
        self._validate_imo_conflict(candidate, existing_vessel)

        if existing_vessel:
            vessel = existing_vessel
        else:
            vessel_payload = self._vessel_payload(candidate)
            upsert_result = self.gateway.upsert_vessel(vessel_payload)
            if not upsert_result:
                raise VesselValidationError("Failed to persist vessel.")

            vessel = upsert_result[0]
            if not vessel.get("id"):
                vessel = self.gateway.get_vessel_by_mmsi(mmsi)
            if not vessel or not vessel.get("id"):
                raise VesselValidationError("Persisted vessel is missing id.")

        tracking_status = self.gateway.activate_tracking_by_vessel(vessel)

        latest_position = candidate.get("latest_position")
        if latest_position:
            try:
                self.gateway.upsert_position_for_vessel(
                    vessel_id=str(vessel["id"]),
                    mmsi=mmsi,
                    position_data=latest_position,
                )
            except Exception:
                warnings.append("Latest position persistence failed.")

        return {
            **self._build_vessel_response(vessel),
            "source": "local",
            "is_persisted": True,
            "is_tracked": bool(tracking_status.get("is_active")),
            "latest_position": (
                {
                    "vessel_id": str(vessel["id"]),
                    **latest_position,
                }
                if latest_position
                else None
            ),
            "warnings": warnings,
        }

    def _validate_imo_conflict(
        self,
        candidate: dict[str, Any],
        existing_vessel: dict[str, Any] | None,
    ) -> None:
        candidate_imo = candidate.get("imo")
        if not candidate_imo:
            return

        vessel_by_imo = self.gateway.get_vessel_by_imo(candidate_imo)
        if not vessel_by_imo:
            return

        candidate_mmsi = candidate.get("mmsi")
        imo_mmsi = normalize_mmsi(vessel_by_imo.get("mmsi"))
        if imo_mmsi and imo_mmsi != candidate_mmsi:
            raise VesselConflictError(
                "IMO is already associated with a different MMSI."
            )

        if existing_vessel and vessel_by_imo.get("id") != existing_vessel.get("id"):
            raise VesselConflictError(
                "IMO is already associated with a different vessel."
            )

    def _build_local_response(self, vessel: dict[str, Any]) -> dict[str, Any]:
        vessel_id = vessel.get("id")
        latest_position = None
        is_tracked = False
        if vessel_id:
            latest_position = self.gateway.get_latest_position_by_vessel_id(
                str(vessel_id)
            )
            tracking_status = self.gateway.get_tracking_status_by_vessel_id(
                str(vessel_id)
            )
            is_tracked = bool(
                tracking_status and tracking_status.get("is_active") is True
            )

        return {
            **self._build_vessel_response(vessel),
            "source": "local",
            "is_persisted": True,
            "is_tracked": is_tracked,
            "latest_position": latest_position,
        }

    def _build_vessel_response(self, vessel: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(vessel["id"]) if vessel.get("id") else None,
            "mmsi": normalize_mmsi(vessel.get("mmsi")),
            "imo": normalize_imo(vessel.get("imo")),
            "name": vessel.get("ship_name") or vessel.get("name"),
            "ship_type": vessel.get("ship_type"),
            "flag_state": vessel.get("flag_state"),
            "callsign": vessel.get("callsign"),
        }

    def _vessel_payload(self, candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            "mmsi": candidate.get("mmsi"),
            "imo": candidate.get("imo"),
            "ship_name": candidate.get("name"),
            "callsign": candidate.get("callsign"),
            "ship_type": candidate.get("ship_type"),
            "flag_state": candidate.get("flag_state"),
            "length_m": candidate.get("length_m"),
            "width_m": candidate.get("width_m"),
            "gross_tonnage": candidate.get("gross_tonnage"),
            "external_source": candidate.get("source") or EXTERNAL_SOURCE_CHINAPORTS,
        }

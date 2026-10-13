from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api.schemas.vessels import (
    LatestPositionResponse,
    TrackPointResponse,
    VesselOnboardRequest,
    VesselOnboardResponse,
    VesselResponse,
    VesselSearchResponse,
)
from risk_monitor.vessel_search_service import (
    ExternalSearchUnsupportedError,
    ExternalSourceUnavailableError,
    VesselConflictError,
    VesselNotFoundError,
    VesselSearchService,
    VesselValidationError,
)


router = APIRouter(
    prefix="/api/v1/vessels",
    tags=["vessels"],
)


class VesselReadRepository:
    def get_tracked_vessels(self) -> list[dict[str, Any]]:
        from risk_monitor.tracking_repository import get_tracked_vessels

        return get_tracked_vessels()

    def get_vessel_by_mmsi(self, mmsi: str) -> dict[str, Any] | None:
        from risk_monitor.vessel_query_repository import get_vessel_by_mmsi

        return get_vessel_by_mmsi(mmsi)

    def get_vessel_by_imo(self, imo: str) -> dict[str, Any] | None:
        from risk_monitor.vessel_query_repository import get_vessel_by_imo

        return get_vessel_by_imo(imo)

    def get_vessel_by_id(self, vessel_id: str) -> dict[str, Any] | None:
        from risk_monitor.vessel_query_repository import get_vessel_by_id

        return get_vessel_by_id(vessel_id)

    def get_latest_position_by_mmsi(self, mmsi: str) -> dict[str, Any] | None:
        from risk_monitor.latest_position_repository import get_latest_position_by_mmsi

        return get_latest_position_by_mmsi(mmsi)

    def get_latest_position_by_vessel_id(
        self,
        vessel_id: str,
    ) -> dict[str, Any] | None:
        from risk_monitor.latest_position_repository import (
            get_latest_position_by_vessel_id,
        )

        return get_latest_position_by_vessel_id(vessel_id)

    def get_track_by_mmsi(self, mmsi: str, limit: int) -> list[dict[str, Any]]:
        from risk_monitor.trajectory_repository import get_vessel_track

        return get_vessel_track(mmsi, limit=limit)

    def get_recorded_vessels(self, limit: int) -> list[dict[str, Any]]:
        from risk_monitor.trajectory_repository import get_recorded_vessels

        return get_recorded_vessels(limit=limit)

    def get_recorded_vessel_by_id(self, vessel_id: str) -> dict[str, Any] | None:
        from risk_monitor.trajectory_repository import get_recorded_vessel_by_id

        return get_recorded_vessel_by_id(vessel_id)


def get_vessel_read_repository() -> VesselReadRepository:
    return VesselReadRepository()


def get_vessel_search_service() -> VesselSearchService:
    return VesselSearchService()


def _server_error(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=500,
        detail="Vessel repository query failed.",
    )


def _to_optional_string(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    return text


def _to_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _tracked_vessel_id(record: dict[str, Any]) -> str | None:
    return _to_optional_string(record.get("vessel_id"))


def _build_vessel_response(
    tracked_vessel: dict[str, Any],
    vessel: dict[str, Any] | None,
) -> VesselResponse | None:
    vessel_id = _tracked_vessel_id(tracked_vessel)
    if not vessel_id:
        return None

    vessel = vessel or {}
    mmsi = _to_optional_string(vessel.get("mmsi")) or _to_optional_string(
        tracked_vessel.get("mmsi")
    )

    return VesselResponse(
        id=vessel_id,
        mmsi=mmsi,
        imo=_to_optional_string(vessel.get("imo")),
        name=_to_optional_string(vessel.get("ship_name")),
        ship_type=_to_optional_string(vessel.get("ship_type")),
        flag_state=_to_optional_string(vessel.get("flag_state")),
        callsign=_to_optional_string(vessel.get("callsign")),
    )


def _build_latest_position_response(
    vessel_id: str | None,
    latest_position: dict[str, Any],
) -> LatestPositionResponse:
    latitude = _to_float(latest_position.get("latitude"))
    longitude = _to_float(latest_position.get("longitude"))
    if latitude is None or longitude is None:
        raise HTTPException(
            status_code=500,
            detail="Latest position has invalid coordinates.",
        )

    return LatestPositionResponse(
        vessel_id=vessel_id,
        latitude=latitude,
        longitude=longitude,
        sog=_to_float(latest_position.get("sog")),
        cog=_to_float(latest_position.get("cog")),
        heading=_to_float(latest_position.get("heading")),
        navigation_status=_to_optional_string(
            latest_position.get(
                "navigation_status",
                latest_position.get("nav_status"),
            )
        ),
        destination=_to_optional_string(latest_position.get("destination")),
        observed_at=latest_position.get("observed_at"),
    )


def _build_track_point_response(
    vessel_id: str,
    point: dict[str, Any],
) -> TrackPointResponse:
    latest = _build_latest_position_response(vessel_id, point)
    return TrackPointResponse(
        **latest.model_dump(),
        id=point.get("id"),
        received_at=point.get("received_at"),
    )


def _find_tracked_vessel(
    tracked_vessels: list[dict[str, Any]],
    vessel_id: str,
) -> dict[str, Any] | None:
    for tracked_vessel in tracked_vessels:
        if _tracked_vessel_id(tracked_vessel) == vessel_id:
            return tracked_vessel

    return None


@router.get("", response_model=list[VesselResponse])
def list_vessels(
    repository: VesselReadRepository = Depends(get_vessel_read_repository),
) -> list[VesselResponse]:
    try:
        tracked_vessels = repository.get_tracked_vessels()
    except Exception as exc:
        raise _server_error(exc) from exc

    response: list[VesselResponse] = []
    for tracked_vessel in tracked_vessels or []:
        vessel = None
        mmsi = _to_optional_string(tracked_vessel.get("mmsi"))
        if mmsi:
            try:
                vessel = repository.get_vessel_by_mmsi(mmsi)
            except Exception as exc:
                raise _server_error(exc) from exc

        vessel_response = _build_vessel_response(
            tracked_vessel,
            vessel,
        )
        if vessel_response:
            response.append(vessel_response)

    return response


@router.get("/search", response_model=VesselSearchResponse)
def search_vessel(
    imo: str | None = Query(default=None),
    mmsi: str | None = Query(default=None),
    service: VesselSearchService = Depends(get_vessel_search_service),
) -> VesselSearchResponse:
    try:
        result = service.search(
            mmsi=mmsi,
            imo=imo,
        )
    except VesselValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    except ExternalSearchUnsupportedError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    except VesselNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except ExternalSourceUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise _server_error(exc) from exc

    return _build_search_response(result)


@router.get("/history/vessels", response_model=list[VesselResponse])
def list_historical_vessels(
    limit: int = Query(default=1000, ge=1, le=5000),
    repository: VesselReadRepository = Depends(get_vessel_read_repository),
) -> list[VesselResponse]:
    try:
        recorded_vessels = repository.get_recorded_vessels(limit)
        response = []
        for recorded in recorded_vessels:
            vessel = repository.get_vessel_by_mmsi(recorded["mmsi"])
            vessel_response = _build_vessel_response(
                {"vessel_id": recorded.get("vessel_id"), "mmsi": recorded["mmsi"]},
                vessel,
            )
            if vessel_response:
                response.append(vessel_response)
        return response
    except Exception as exc:
        raise _server_error(exc) from exc


@router.post("/onboard", response_model=VesselOnboardResponse)
def onboard_vessel(
    request: VesselOnboardRequest,
    service: VesselSearchService = Depends(get_vessel_search_service),
) -> VesselOnboardResponse:
    try:
        result = service.onboard(request.model_dump(mode="python"))
    except VesselValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    except VesselConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise _server_error(exc) from exc

    return VesselOnboardResponse(
        **_build_search_response(result).model_dump(),
        warnings=result.get("warnings") or [],
    )


@router.get("/{vessel_id}/latest-position", response_model=LatestPositionResponse)
def get_latest_position(
    vessel_id: str,
    repository: VesselReadRepository = Depends(get_vessel_read_repository),
) -> LatestPositionResponse:
    normalized_vessel_id = vessel_id.strip()
    try:
        tracked_vessels = repository.get_tracked_vessels()
    except Exception as exc:
        raise _server_error(exc) from exc

    if not _find_tracked_vessel(
        tracked_vessels or [],
        normalized_vessel_id,
    ):
        raise HTTPException(
            status_code=404,
            detail="Vessel not found.",
        )

    try:
        latest_position = repository.get_latest_position_by_vessel_id(
            normalized_vessel_id
        )
    except Exception as exc:
        raise _server_error(exc) from exc

    if not latest_position:
        raise HTTPException(
            status_code=404,
            detail="Latest position not found.",
        )

    return _build_latest_position_response(
        vessel_id=normalized_vessel_id,
        latest_position=latest_position,
    )


@router.get("/{vessel_id}/track", response_model=list[TrackPointResponse])
def get_vessel_track(
    vessel_id: str,
    limit: int = Query(default=1000, ge=1, le=5000),
    repository: VesselReadRepository = Depends(get_vessel_read_repository),
) -> list[TrackPointResponse]:
    normalized_vessel_id = vessel_id.strip()
    try:
        vessel = repository.get_vessel_by_id(normalized_vessel_id)
    except Exception as exc:
        raise _server_error(exc) from exc

    if not vessel:
        raise HTTPException(status_code=404, detail="Vessel not found.")

    mmsi = _to_optional_string(vessel.get("mmsi"))
    if not mmsi:
        raise HTTPException(status_code=404, detail="Vessel has no MMSI.")

    try:
        points = repository.get_track_by_mmsi(mmsi, limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise _server_error(exc) from exc

    return [_build_track_point_response(normalized_vessel_id, point) for point in points]


def _build_search_response(result: dict[str, Any]) -> VesselSearchResponse:
    latest_position = result.get("latest_position")
    latest_position_response = None
    if latest_position:
        vessel_id = result.get("id") or latest_position.get("vessel_id")
        latest_position_response = _build_latest_position_response(
            vessel_id=str(vessel_id) if vessel_id else None,
            latest_position=latest_position,
        )

    return VesselSearchResponse(
        id=_to_optional_string(result.get("id")),
        mmsi=_to_optional_string(result.get("mmsi")),
        imo=_to_optional_string(result.get("imo")),
        name=_to_optional_string(result.get("name")),
        ship_type=_to_optional_string(result.get("ship_type")),
        flag_state=_to_optional_string(result.get("flag_state")),
        callsign=_to_optional_string(result.get("callsign")),
        source=_to_optional_string(result.get("source")) or "local",
        is_persisted=bool(result.get("is_persisted")),
        is_tracked=bool(result.get("is_tracked")),
        latest_position=latest_position_response,
    )

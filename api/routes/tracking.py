from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.schemas.vessels import TrackingStatusResponse, TrackingStatusUpdate


router = APIRouter(
    prefix="/api/v1/tracking/vessels",
    tags=["tracking"],
)


class TrackingManagementRepository:
    def get_vessel_by_id(self, vessel_id: str) -> dict[str, Any] | None:
        from risk_monitor.vessel_query_repository import get_vessel_by_id

        return get_vessel_by_id(vessel_id)

    def activate_tracking_by_vessel(
        self,
        vessel: dict[str, Any],
    ) -> dict[str, Any]:
        from risk_monitor.tracking_repository import activate_tracking_by_vessel

        return activate_tracking_by_vessel(vessel)

    def deactivate_tracking_by_vessel_id(
        self,
        vessel_id: str,
    ) -> dict[str, Any] | None:
        from risk_monitor.tracking_repository import deactivate_tracking_by_vessel_id

        return deactivate_tracking_by_vessel_id(vessel_id)


def get_tracking_management_repository() -> TrackingManagementRepository:
    return TrackingManagementRepository()


def _server_error(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=500,
        detail="Tracking repository query failed.",
    )


def _normalize_vessel_id(vessel_id: str) -> str:
    normalized_vessel_id = str(vessel_id or "").strip()
    if not normalized_vessel_id:
        raise HTTPException(
            status_code=422,
            detail="vessel_id is required.",
        )

    return normalized_vessel_id


def _ensure_vessel_exists(
    vessel_id: str,
    repository: TrackingManagementRepository,
) -> dict[str, Any]:
    try:
        vessel = repository.get_vessel_by_id(vessel_id)
    except Exception as exc:
        raise _server_error(exc) from exc

    if not vessel:
        raise HTTPException(
            status_code=404,
            detail="Vessel not found.",
        )

    return vessel


@router.post("/{vessel_id}", response_model=TrackingStatusResponse)
def activate_tracking(
    vessel_id: str,
    repository: TrackingManagementRepository = Depends(
        get_tracking_management_repository
    ),
) -> TrackingStatusResponse:
    normalized_vessel_id = _normalize_vessel_id(vessel_id)
    vessel = _ensure_vessel_exists(
        normalized_vessel_id,
        repository,
    )

    try:
        tracking_status = repository.activate_tracking_by_vessel(vessel)
    except Exception as exc:
        raise _server_error(exc) from exc

    return TrackingStatusResponse(
        vessel_id=normalized_vessel_id,
        is_active=bool(tracking_status.get("is_active")),
    )


@router.patch("/{vessel_id}", response_model=TrackingStatusResponse)
def update_tracking_status(
    vessel_id: str,
    update: TrackingStatusUpdate,
    repository: TrackingManagementRepository = Depends(
        get_tracking_management_repository
    ),
) -> TrackingStatusResponse:
    if update.is_active:
        raise HTTPException(
            status_code=422,
            detail="Only deactivation is supported by this endpoint.",
        )

    normalized_vessel_id = _normalize_vessel_id(vessel_id)
    _ensure_vessel_exists(
        normalized_vessel_id,
        repository,
    )

    try:
        repository.deactivate_tracking_by_vessel_id(normalized_vessel_id)
    except Exception as exc:
        raise _server_error(exc) from exc

    return TrackingStatusResponse(
        vessel_id=normalized_vessel_id,
        is_active=False,
    )

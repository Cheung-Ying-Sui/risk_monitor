from __future__ import annotations

import logging
import time
from typing import Any

from risk_monitor.rolling_route_repository import get_rolling_route_prediction


logger = logging.getLogger(__name__)


def refresh_insurance_voyages(vessel_id, mmsi):
    from risk_monitor.navigation.insurance_prediction_service import InsuranceVoyagePredictionService
    from risk_monitor.rolling_route_repository import get_active_route_prediction
    service = InsuranceVoyagePredictionService()
    rows = service.list_predictions(refresh=True, vessel_id=vessel_id)
    if rows:
        route = next((r for r in rows if r['prediction']), rows[0])
        return {'status': route['status'], 'route_updated': False,
                'active_route': {'route_prediction_id': route['route_prediction_id']},
                'warnings': route['warnings']}
    previous = get_active_route_prediction(mmsi)
    if previous and (previous.get('route_geojson') or {}).get('insurance_voyage'):
        return {'status': 'voyage_completed', 'route_updated': False, 'warnings': ['no_active_insurance_voyage']}
    return None


def refresh_prediction_after_position(
    *,
    vessel_id: str,
    mmsi: str,
    observed_at: Any = None,
) -> dict[str, Any]:
    """Refresh prediction after AIS persistence without propagating failures."""

    normalized_vessel_id = str(vessel_id or "").strip()
    normalized_mmsi = str(mmsi or "").strip()
    if not normalized_vessel_id or not normalized_mmsi:
        return {
            "status": "skipped",
            "vessel_id": normalized_vessel_id or None,
            "mmsi": normalized_mmsi or None,
            "reason": "missing_vessel_identity",
        }

    started_at = time.perf_counter()
    try:
        result = refresh_insurance_voyages(normalized_vessel_id, normalized_mmsi)
        if result is None:
            result = get_rolling_route_prediction(normalized_mmsi)
    except Exception as exc:
        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.exception(
            "navigation_prediction_refresh_failed vessel_id=%s mmsi=%s "
            "observed_at=%s latency_ms=%s",
            normalized_vessel_id,
            normalized_mmsi,
            observed_at,
            latency_ms,
        )
        return {
            "status": "failed",
            "vessel_id": normalized_vessel_id,
            "mmsi": normalized_mmsi,
            "observed_at": observed_at,
            "error_type": type(exc).__name__,
            "latency_ms": latency_ms,
        }

    active_route = result.get("active_route") or {}
    latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
    status = "updated" if result.get("route_updated") else result.get("status")
    logger.info(
        "navigation_prediction_refresh_completed vessel_id=%s mmsi=%s "
        "observed_at=%s status=%s prediction_id=%s route_updated=%s "
        "route_progress_pending=true latency_ms=%s",
        normalized_vessel_id,
        normalized_mmsi,
        observed_at,
        status,
        active_route.get("route_prediction_id"),
        bool(result.get("route_updated")),
        latency_ms,
    )
    return {
        "status": status,
        "vessel_id": normalized_vessel_id,
        "mmsi": normalized_mmsi,
        "observed_at": observed_at,
        "prediction_id": active_route.get("route_prediction_id"),
        "route_updated": bool(result.get("route_updated")),
        "route_update_reason": result.get("route_update_reason"),
        "warnings": result.get("warnings") or [],
        "latency_ms": latency_ms,
    }

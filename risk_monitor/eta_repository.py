from __future__ import annotations

from datetime import datetime, timedelta, timezone

from risk_monitor.navigation.destination_normalizer import resolve_destination
from risk_monitor.navigation.eta_engine import estimate_eta, estimate_sailing_speed
from risk_monitor.navigation.route_engine import estimate_navigable_route
from risk_monitor.supabase_client import supabase


LATEST_POSITION_FIELDS = (
    "vessel_id,position_id,mmsi,latitude,longitude,sog,cog,heading,"
    "destination,nav_status,observed_at,received_at,source_id"
)

POSITION_HISTORY_FIELDS = "mmsi,sog,observed_at"
LATEST_AIS_ETA_FIELDS = "id,eta"


def _normalize_mmsi(mmsi):
    if not mmsi:
        raise ValueError("mmsi is required.")

    normalized_mmsi = str(mmsi).strip()
    if not normalized_mmsi:
        raise ValueError("mmsi is required.")

    return normalized_mmsi


def _utc_now():
    return datetime.now(timezone.utc)


def _since_iso(hours, now):
    return (now - timedelta(hours=hours)).isoformat()


def get_latest_position_for_eta(mmsi):
    result = (
        supabase
        .schema("tracking")
        .table("latest_vessel_positions")
        .select(LATEST_POSITION_FIELDS)
        .eq(
            "mmsi",
            _normalize_mmsi(mmsi),
        )
        .limit(1)
        .execute()
    )

    if not result.data:
        return None

    latest_position = result.data[0]
    position_id = latest_position.get("position_id")
    if not position_id:
        return latest_position

    eta_result = (
        supabase
        .schema("tracking")
        .table("vessel_positions")
        .select(LATEST_AIS_ETA_FIELDS)
        .eq(
            "id",
            position_id,
        )
        .limit(1)
        .execute()
    )

    if eta_result.data:
        latest_position["eta"] = eta_result.data[0].get("eta")

    return latest_position


def get_sog_history(mmsi, hours=None, limit=1000, now=None):
    query = (
        supabase
        .schema("tracking")
        .table("vessel_positions")
        .select(POSITION_HISTORY_FIELDS)
        .eq(
            "mmsi",
            _normalize_mmsi(mmsi),
        )
    )

    if hours is not None:
        query = query.gte(
            "observed_at",
            _since_iso(hours, now or _utc_now()),
        )

    result = (
        query
        .order(
            "observed_at",
            desc=True,
        )
        .limit(int(limit))
        .execute()
    )

    return result.data or []


def _unavailable_result(mmsi, warning, calculated_at=None):
    calculated_at = calculated_at or _utc_now()
    return {
        "status": "unavailable",
        "mmsi": str(mmsi) if mmsi is not None else None,
        "destination_raw": None,
        "destination_normalized": None,
        "destination_latitude": None,
        "destination_longitude": None,
        "destination_unlocode": None,
        "remaining_distance_nm": None,
        "great_circle_distance_nm": None,
        "navigable_distance_nm": None,
        "route_distance_ratio": None,
        "distance_method": "great_circle_baseline",
        "route_method": None,
        "estimated_route_geojson": None,
        "estimated_speed_knots": None,
        "speed_method": "unavailable",
        "estimated_remaining_hours": None,
        "estimated_arrival_at": None,
        "baseline_estimated_eta": None,
        "reported_ais_eta": None,
        "eta_difference_hours": None,
        "calculated_at": calculated_at.isoformat(),
        "confidence": "low",
        "warnings": [warning],
        "resolution_status": None,
        "resolution_method": None,
        "speed_sample_count": 0,
        "speed_variability": None,
        "speed_variability_method": "moving_sog_stddev",
    }


def get_vessel_eta_estimate(mmsi):
    calculated_at = _utc_now()

    try:
        normalized_mmsi = _normalize_mmsi(mmsi)
        latest_position = get_latest_position_for_eta(normalized_mmsi)
    except Exception as exc:
        return _unavailable_result(
            mmsi,
            f"repository_failure:{exc}",
            calculated_at=calculated_at,
        )

    if not latest_position:
        return _unavailable_result(
            mmsi,
            "no_latest_position",
            calculated_at=calculated_at,
        )

    try:
        recent_6h_positions = get_sog_history(
            normalized_mmsi,
            hours=6,
            now=calculated_at,
        )
        recent_24h_positions = get_sog_history(
            normalized_mmsi,
            hours=24,
            now=calculated_at,
        )
        historical_positions = get_sog_history(
            normalized_mmsi,
            hours=None,
            now=calculated_at,
        )
    except Exception as exc:
        return _unavailable_result(
            mmsi,
            f"repository_failure:{exc}",
            calculated_at=calculated_at,
        )

    speed_context = estimate_sailing_speed(
        recent_6h_positions=recent_6h_positions,
        recent_24h_positions=recent_24h_positions,
        historical_positions=historical_positions,
        current_sog=latest_position.get("sog"),
    )
    destination_resolution = resolve_destination(
        latest_position.get("destination")
    )
    route_result = None
    if destination_resolution.get("resolution_status") == "resolved":
        try:
            route_result = estimate_navigable_route(
                latest_position.get("latitude"),
                latest_position.get("longitude"),
                destination_resolution.get("latitude"),
                destination_resolution.get("longitude"),
            )
        except Exception as exc:
            route_result = {
                "status": "unavailable",
                "route_method": "land_avoidance_baseline",
                "distance_method": "great_circle_baseline",
                "estimated_route_geojson": None,
                "warnings": [
                    f"navigable_route_unavailable:{exc}",
                ],
            }

    return estimate_eta(
        latest_position,
        destination=latest_position.get("destination"),
        speed_context=speed_context,
        destination_resolution=destination_resolution,
        route_result=route_result,
        calculated_at=calculated_at,
    )

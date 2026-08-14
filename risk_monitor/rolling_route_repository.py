from __future__ import annotations

from datetime import datetime, timezone

from risk_monitor.eta_repository import get_sog_history
from risk_monitor.latest_position_repository import get_latest_position_by_mmsi
from risk_monitor.navigation.destination_normalizer import resolve_destination
from risk_monitor.navigation.eta_engine import estimate_eta, estimate_sailing_speed
from risk_monitor.navigation.route_engine import estimate_navigable_route
from risk_monitor.navigation.route_monitor import evaluate_route_deviation
from risk_monitor.supabase_client import supabase
from risk_monitor.trajectory_repository import get_track_points_after_prediction


ROUTE_UPDATE_REASON_INITIAL = "initial_route"
ROUTE_UPDATE_REASON_DESTINATION_CHANGED = "destination_changed"
ROUTE_UPDATE_REASON_ROUTE_DEVIATION = "route_deviation"
ROUTE_UPDATE_REASON_MANUAL_REFRESH = "manual_refresh"

ROUTE_UPDATE_REASONS = {
    ROUTE_UPDATE_REASON_INITIAL,
    ROUTE_UPDATE_REASON_DESTINATION_CHANGED,
    ROUTE_UPDATE_REASON_ROUTE_DEVIATION,
    ROUTE_UPDATE_REASON_MANUAL_REFRESH,
}

ACTIVE_ROUTE_FIELDS = (
    "id,vessel_id,mmsi,origin_position_id,destination_raw,"
    "destination_normalized,destination_unlocode,route_version,route_method,"
    "route_geojson,great_circle_distance_nm,navigable_distance_nm,"
    "route_distance_ratio,route_created_at,route_update_reason,status,"
    "superseded_at,request_id,created_at"
)


def _normalize_mmsi(mmsi):
    if not mmsi:
        raise ValueError("mmsi is required.")

    normalized = str(mmsi).strip()
    if not normalized:
        raise ValueError("mmsi is required.")

    return normalized


def _to_int(value):
    if value is None:
        return None
    return int(value)


def _request_id(mmsi, origin_position_id, update_reason, destination_unlocode):
    origin_key = origin_position_id if origin_position_id is not None else "no-origin"
    destination_key = destination_unlocode or "unresolved"
    return f"{mmsi}:{origin_key}:{update_reason}:{destination_key}"


def _destination_key(destination_resolution, fallback_raw=None):
    destination_resolution = destination_resolution or {}
    return (
        destination_resolution.get("unlocode")
        or destination_resolution.get("normalized_destination")
        or destination_resolution.get("compact_input")
        or fallback_raw
    )


def _destination_changed(active_route, destination_resolution, latest_position):
    if not active_route:
        return False

    previous_key = (
        active_route.get("destination_unlocode")
        or active_route.get("destination_normalized")
        or active_route.get("destination_raw")
    )
    current_key = _destination_key(
        destination_resolution,
        fallback_raw=latest_position.get("destination") if latest_position else None,
    )
    return bool(previous_key and current_key and previous_key != current_key)


def _route_result_from_prediction(route_prediction):
    if not route_prediction:
        return None

    return {
        "status": "estimated",
        "route_method": route_prediction.get("route_method"),
        "distance_method": "navigable_route_baseline",
        "great_circle_distance_nm": route_prediction.get("great_circle_distance_nm"),
        "navigable_distance_nm": route_prediction.get("navigable_distance_nm"),
        "route_distance_ratio": route_prediction.get("route_distance_ratio"),
        "estimated_route_geojson": route_prediction.get("route_geojson"),
        "warnings": [],
    }


def _estimate_eta_for_route(latest_position, destination_resolution, route_prediction):
    speed_context = estimate_sailing_speed(
        recent_6h_positions=get_sog_history(latest_position.get("mmsi"), hours=6),
        recent_24h_positions=get_sog_history(latest_position.get("mmsi"), hours=24),
        historical_positions=get_sog_history(latest_position.get("mmsi")),
        current_sog=latest_position.get("sog"),
    )
    return estimate_eta(
        latest_position,
        destination=latest_position.get("destination"),
        speed_context=speed_context,
        destination_resolution=destination_resolution,
        route_result=_route_result_from_prediction(route_prediction),
        calculated_at=datetime.now(timezone.utc),
    )


def _route_prediction_from_db(record):
    if not record:
        return None

    return {
        "route_prediction_id": record.get("id"),
        "vessel_id": record.get("vessel_id"),
        "mmsi": record.get("mmsi"),
        "origin_position_id": record.get("origin_position_id"),
        "destination_raw": record.get("destination_raw"),
        "destination_normalized": record.get("destination_normalized"),
        "destination_unlocode": record.get("destination_unlocode"),
        "route_version": record.get("route_version"),
        "route_method": record.get("route_method"),
        "distance_method": "navigable_route_baseline",
        "route_geojson": record.get("route_geojson"),
        "great_circle_distance_nm": record.get("great_circle_distance_nm"),
        "navigable_distance_nm": record.get("navigable_distance_nm"),
        "route_distance_ratio": record.get("route_distance_ratio"),
        "route_created_at": record.get("route_created_at"),
        "route_update_reason": record.get("route_update_reason"),
        "status": record.get("status"),
        "superseded_at": record.get("superseded_at"),
        "request_id": record.get("request_id"),
        "created_at": record.get("created_at"),
        "origin": {
            "position_id": record.get("origin_position_id"),
        },
    }


def _fetch_route_prediction(route_prediction_id):
    result = (
        supabase
        .schema("tracking")
        .rpc(
            "get_route_prediction",
            {
                "p_route_prediction_id": route_prediction_id,
            },
        )
        .execute()
    )
    if not result.data:
        return None
    return _route_prediction_from_db(result.data[0])


def get_active_route_prediction(mmsi):
    result = (
        supabase
        .schema("tracking")
        .rpc(
            "get_active_route_prediction",
            {
                "p_mmsi": _normalize_mmsi(mmsi),
            },
        )
        .execute()
    )
    if not result.data:
        return None
    return _route_prediction_from_db(result.data[0])


def create_route_prediction(route_snapshot):
    rpc_result = (
        supabase
        .schema("tracking")
        .rpc(
            "activate_route_prediction",
            {
                "p_vessel_id": route_snapshot.get("vessel_id"),
                "p_mmsi": route_snapshot.get("mmsi"),
                "p_origin_position_id": route_snapshot.get("origin_position_id"),
                "p_destination_raw": route_snapshot.get("destination_raw"),
                "p_destination_normalized": route_snapshot.get(
                    "destination_normalized"
                ),
                "p_destination_unlocode": route_snapshot.get("destination_unlocode"),
                "p_route_method": route_snapshot.get("route_method"),
                "p_route_geojson": route_snapshot.get("route_geojson"),
                "p_great_circle_distance_nm": route_snapshot.get(
                    "great_circle_distance_nm"
                ),
                "p_navigable_distance_nm": route_snapshot.get(
                    "navigable_distance_nm"
                ),
                "p_route_distance_ratio": route_snapshot.get("route_distance_ratio"),
                "p_route_update_reason": route_snapshot.get("route_update_reason"),
                "p_request_id": route_snapshot.get("request_id"),
            },
        )
        .execute()
    )
    if not rpc_result.data:
        raise RuntimeError("activate_route_prediction returned no data.")

    activation = rpc_result.data[0]
    route_prediction = _fetch_route_prediction(
        activation.get("route_prediction_id")
    )
    if not route_prediction:
        raise RuntimeError("activated route prediction could not be read.")

    route_prediction["activation"] = activation
    return route_prediction


def supersede_route_prediction(route_prediction_id):
    result = (
        supabase
        .schema("tracking")
        .rpc(
            "supersede_route_prediction",
            {
                "p_route_prediction_id": route_prediction_id,
            },
        )
        .execute()
    )
    return result.data or []


def _generate_route_snapshot(latest_position, destination_resolution, update_reason):
    route_result = estimate_navigable_route(
        latest_position.get("latitude"),
        latest_position.get("longitude"),
        destination_resolution.get("latitude"),
        destination_resolution.get("longitude"),
    )
    origin_position_id = _to_int(latest_position.get("position_id"))
    destination_unlocode = destination_resolution.get("unlocode")
    normalized_mmsi = _normalize_mmsi(latest_position.get("mmsi"))

    return {
        "vessel_id": latest_position.get("vessel_id"),
        "mmsi": normalized_mmsi,
        "origin_position_id": origin_position_id,
        "destination_raw": destination_resolution.get("raw_destination"),
        "destination_normalized": destination_resolution.get(
            "normalized_destination"
        ),
        "destination_unlocode": destination_unlocode,
        "route_method": route_result.get("route_method"),
        "route_geojson": route_result.get("estimated_route_geojson"),
        "great_circle_distance_nm": route_result.get("great_circle_distance_nm"),
        "navigable_distance_nm": route_result.get("navigable_distance_nm"),
        "route_distance_ratio": route_result.get("route_distance_ratio"),
        "route_update_reason": update_reason,
        "request_id": _request_id(
            normalized_mmsi,
            origin_position_id,
            update_reason,
            destination_unlocode,
        ),
    }


def _new_points_since_route(mmsi, active_route):
    return get_track_points_after_prediction(
        mmsi,
        origin_position_id=active_route.get("origin_position_id"),
        route_created_at=active_route.get("route_created_at"),
    )


def _awaiting_new_ais_result(active_route):
    return {
        "status": "awaiting_new_ais_position",
        "distance_to_route_nm": None,
        "expected_route_bearing_deg": None,
        "current_cog_deg": None,
        "course_difference_deg": None,
        "distance_deviation": False,
        "course_deviation": False,
        "consecutive_deviation_points": 0,
        "required_consecutive_deviation_points": 3,
        "recalculation_recommended": False,
        "reasons": ["awaiting_new_ais_position"],
        "route_created_at": active_route.get("route_created_at"),
        "route_origin": active_route.get("origin"),
    }


def _evaluate_persisted_route(active_route, new_points):
    if not new_points:
        return _awaiting_new_ais_result(active_route)

    current_position = new_points[-1]
    return evaluate_route_deviation(
        current_position,
        current_position.get("cog"),
        active_route.get("route_geojson"),
        route_created_at=active_route.get("route_created_at"),
        route_origin=active_route.get("origin"),
        recent_positions=new_points,
    )


def _result(
    mmsi,
    latest_position,
    destination_resolution,
    active_route,
    deviation_result,
    new_points,
    route_updated=False,
    previous_route=None,
    warnings=None,
):
    eta_result = _estimate_eta_for_route(
        latest_position,
        destination_resolution,
        active_route,
    )
    return {
        "status": "estimated",
        "mmsi": mmsi,
        "route_updated": route_updated,
        "route_update_reason": active_route.get("route_update_reason"),
        "previous_route": previous_route,
        "new_route": active_route if route_updated else None,
        "active_route": active_route,
        "deviation_result": deviation_result,
        "latest_position": latest_position,
        "destination_resolution": destination_resolution,
        "recent_positions": new_points,
        "new_ais_points_since_prediction": len(new_points),
        "monitoring_since": active_route.get("route_created_at"),
        "warnings": warnings or [],
        "eta_result": eta_result,
    }


def get_rolling_route_prediction(mmsi, update_reason=None):
    normalized_mmsi = _normalize_mmsi(mmsi)
    if update_reason and update_reason not in ROUTE_UPDATE_REASONS:
        raise ValueError("invalid route update reason.")

    latest_position = get_latest_position_by_mmsi(normalized_mmsi)
    if not latest_position:
        return {
            "status": "unavailable",
            "mmsi": normalized_mmsi,
            "route_updated": False,
            "route_update_reason": None,
            "previous_route": None,
            "new_route": None,
            "active_route": None,
            "deviation_result": None,
            "latest_position": None,
            "destination_resolution": None,
            "recent_positions": [],
            "new_ais_points_since_prediction": 0,
            "monitoring_since": None,
            "warnings": ["no_latest_position"],
        }

    destination_resolution = resolve_destination(latest_position.get("destination"))
    if destination_resolution.get("resolution_status") != "resolved":
        return {
            "status": "unavailable",
            "mmsi": normalized_mmsi,
            "route_updated": False,
            "route_update_reason": None,
            "previous_route": get_active_route_prediction(normalized_mmsi),
            "new_route": None,
            "active_route": get_active_route_prediction(normalized_mmsi),
            "deviation_result": None,
            "latest_position": latest_position,
            "destination_resolution": destination_resolution,
            "recent_positions": [],
            "new_ais_points_since_prediction": 0,
            "monitoring_since": None,
            "warnings": destination_resolution.get("warnings")
            or ["destination_unresolved"],
        }

    active_route = get_active_route_prediction(normalized_mmsi)
    if not active_route:
        active_route = create_route_prediction(
            _generate_route_snapshot(
                latest_position,
                destination_resolution,
                update_reason or ROUTE_UPDATE_REASON_INITIAL,
            )
        )
        new_points = _new_points_since_route(normalized_mmsi, active_route)
        deviation_result = _evaluate_persisted_route(active_route, new_points)
        return _result(
            normalized_mmsi,
            latest_position,
            destination_resolution,
            active_route,
            deviation_result,
            new_points,
            route_updated=True,
        )

    destination_changed = _destination_changed(
        active_route,
        destination_resolution,
        latest_position,
    )
    if update_reason == ROUTE_UPDATE_REASON_MANUAL_REFRESH or destination_changed:
        reason = (
            ROUTE_UPDATE_REASON_MANUAL_REFRESH
            if update_reason == ROUTE_UPDATE_REASON_MANUAL_REFRESH
            else ROUTE_UPDATE_REASON_DESTINATION_CHANGED
        )
        previous_route = active_route
        active_route = create_route_prediction(
            _generate_route_snapshot(
                latest_position,
                destination_resolution,
                reason,
            )
        )
        new_points = _new_points_since_route(normalized_mmsi, active_route)
        deviation_result = _evaluate_persisted_route(active_route, new_points)
        return _result(
            normalized_mmsi,
            latest_position,
            destination_resolution,
            active_route,
            deviation_result,
            new_points,
            route_updated=True,
            previous_route=previous_route,
        )

    new_points = _new_points_since_route(normalized_mmsi, active_route)
    deviation_result = _evaluate_persisted_route(active_route, new_points)
    if deviation_result.get("recalculation_recommended"):
        previous_route = active_route
        active_route = create_route_prediction(
            _generate_route_snapshot(
                latest_position,
                destination_resolution,
                ROUTE_UPDATE_REASON_ROUTE_DEVIATION,
            )
        )
        new_points = _new_points_since_route(normalized_mmsi, active_route)
        post_update_deviation = _evaluate_persisted_route(active_route, new_points)
        return _result(
            normalized_mmsi,
            latest_position,
            destination_resolution,
            active_route,
            post_update_deviation,
            new_points,
            route_updated=True,
            previous_route=previous_route,
        )

    return _result(
        normalized_mmsi,
        latest_position,
        destination_resolution,
        active_route,
        deviation_result,
        new_points,
        route_updated=False,
    )

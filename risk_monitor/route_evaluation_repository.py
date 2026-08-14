from __future__ import annotations

from risk_monitor.navigation.route_evaluation import (
    evaluate_actual_track_against_route,
)
from risk_monitor.rolling_route_repository import (
    _normalize_mmsi,
    _route_prediction_from_db,
)
from risk_monitor.supabase_client import supabase
from risk_monitor.trajectory_repository import get_track_points_after_prediction


def get_route_prediction_history(mmsi):
    result = (
        supabase
        .schema("tracking")
        .rpc(
            "get_route_prediction_history",
            {
                "p_mmsi": _normalize_mmsi(mmsi),
            },
        )
        .execute()
    )
    return [
        _route_prediction_from_db(record)
        for record in result.data or []
    ]


def _select_route_prediction(history, route_prediction_id=None, route_version=None):
    if route_prediction_id:
        for route_prediction in history:
            if str(route_prediction.get("route_prediction_id")) == str(
                route_prediction_id
            ):
                return route_prediction
        return None

    if route_version is not None:
        version = int(route_version)
        for route_prediction in history:
            if route_prediction.get("route_version") == version:
                return route_prediction
        return None

    active_routes = [
        route_prediction
        for route_prediction in history
        if route_prediction.get("status") == "active"
    ]
    if active_routes:
        return active_routes[-1]
    if history:
        return history[-1]
    return None


def _actual_track_for_prediction(mmsi, route_prediction):
    return get_track_points_after_prediction(
        mmsi,
        origin_position_id=route_prediction.get("origin_position_id"),
        route_created_at=route_prediction.get("route_created_at"),
        until_observed_at=route_prediction.get("superseded_at"),
    )


def _evaluation_status(route_prediction, evaluation):
    if evaluation.get("status") in {"awaiting_data", "unavailable"}:
        return evaluation.get("status")
    if route_prediction.get("status") == "superseded":
        return "superseded"
    return evaluation.get("status")


def evaluate_route_prediction(
    mmsi,
    route_prediction_id=None,
    route_version=None,
):
    normalized_mmsi = _normalize_mmsi(mmsi)
    history = get_route_prediction_history(normalized_mmsi)
    route_prediction = _select_route_prediction(
        history,
        route_prediction_id=route_prediction_id,
        route_version=route_version,
    )
    if not route_prediction:
        return {
            "status": "unavailable",
            "mmsi": normalized_mmsi,
            "route_prediction": None,
            "route_prediction_id": route_prediction_id,
            "route_version": route_version,
            "predicted_route": None,
            "actual_track": [],
            "point_errors": [],
            "observation_count": 0,
            "mean_deviation_nm": None,
            "median_deviation_nm": None,
            "max_deviation_nm": None,
            "p90_deviation_nm": None,
            "route_adherence_ratio": None,
            "route_progress_ratio": None,
            "reasons": ["route_prediction_not_found"],
        }

    actual_track = _actual_track_for_prediction(
        normalized_mmsi,
        route_prediction,
    )
    evaluation = evaluate_actual_track_against_route(
        route_prediction.get("route_geojson"),
        actual_track,
    )
    status = _evaluation_status(route_prediction, evaluation)

    return {
        "status": status,
        "route_following_status": evaluation.get("status"),
        "mmsi": normalized_mmsi,
        "route_prediction": route_prediction,
        "route_prediction_id": route_prediction.get("route_prediction_id"),
        "route_version": route_prediction.get("route_version"),
        "predicted_route": route_prediction.get("route_geojson"),
        "actual_track": actual_track,
        "point_errors": evaluation.get("point_errors") or [],
        "observation_count": evaluation.get("observation_count"),
        "mean_deviation_nm": evaluation.get("mean_deviation_nm"),
        "median_deviation_nm": evaluation.get("median_deviation_nm"),
        "max_deviation_nm": evaluation.get("max_deviation_nm"),
        "p90_deviation_nm": evaluation.get("p90_deviation_nm"),
        "route_adherence_ratio": evaluation.get("route_adherence_ratio"),
        "route_progress_ratio": evaluation.get("route_progress_ratio"),
        "adherence_threshold_nm": evaluation.get("adherence_threshold_nm"),
        "destination_raw": route_prediction.get("destination_raw"),
        "destination_normalized": route_prediction.get("destination_normalized"),
        "destination_unlocode": route_prediction.get("destination_unlocode"),
        "route_method": route_prediction.get("route_method"),
        "route_created_at": route_prediction.get("route_created_at"),
        "superseded_at": route_prediction.get("superseded_at"),
        "route_update_reason": route_prediction.get("route_update_reason"),
        "reasons": evaluation.get("reasons") or [],
    }

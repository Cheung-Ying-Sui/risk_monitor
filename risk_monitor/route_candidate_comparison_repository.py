from __future__ import annotations

from risk_monitor.navigation.route_evaluation import (
    evaluate_actual_track_against_route,
)
from risk_monitor.navigation.route_corridor_scorer import (
    rank_route_candidates,
)
from risk_monitor.navigation.route_prior import apply_shipping_lane_prior
from risk_monitor.navigation.routeing_feature_adapter import (
    adapt_routeing_features_for_prior,
)
from risk_monitor.navigation.shipping_lane_provider import (
    load_official_routeing_reference,
    load_poc_shipping_lane_reference,
)
from risk_monitor.route_evaluation_repository import (
    _actual_track_for_prediction,
    _select_route_prediction,
    get_route_prediction_history,
)
from risk_monitor.rolling_route_repository import _normalize_mmsi


def _baseline_route_result(route_prediction):
    return {
        "status": "estimated",
        "route_method": route_prediction.get("route_method"),
        "distance_method": route_prediction.get("distance_method"),
        "great_circle_distance_nm": route_prediction.get("great_circle_distance_nm"),
        "navigable_distance_nm": route_prediction.get("navigable_distance_nm"),
        "route_distance_ratio": route_prediction.get("route_distance_ratio"),
        "estimated_route_geojson": route_prediction.get("route_geojson"),
        "warnings": [],
    }


def _route_for_candidate(candidate_id, route_result):
    return {
        **route_result,
        "candidate_id": candidate_id,
    }


def _improvement(current_metrics, candidate_metrics):
    baseline_mean = current_metrics.get("mean_deviation_nm")
    candidate_mean = candidate_metrics.get("mean_deviation_nm")
    baseline_adherence = current_metrics.get("route_adherence_ratio")
    candidate_adherence = candidate_metrics.get("route_adherence_ratio")

    mean_improvement = None
    mean_improvement_pct = None
    if baseline_mean is not None and candidate_mean is not None:
        mean_improvement = baseline_mean - candidate_mean
        if baseline_mean:
            mean_improvement_pct = mean_improvement / baseline_mean

    adherence_improvement = None
    if baseline_adherence is not None and candidate_adherence is not None:
        adherence_improvement = candidate_adherence - baseline_adherence

    return {
        "mean_deviation_improvement_nm": mean_improvement,
        "mean_deviation_improvement_pct": mean_improvement_pct,
        "adherence_improvement": adherence_improvement,
        "candidate_performs_better": bool(
            mean_improvement is not None
            and mean_improvement > 0
            and (
                adherence_improvement is None
                or adherence_improvement >= 0
            )
        ),
    }


def _candidate_for_reference(current_route, actual_track, lane_reference, use_adapter):
    features = lane_reference.get("features") or []
    if use_adapter:
        features = adapt_routeing_features_for_prior(features)
    candidate_route = apply_shipping_lane_prior(
        _baseline_route_result(current_route),
        lane_features=features,
    )
    candidate_metrics = evaluate_actual_track_against_route(
        candidate_route.get("estimated_route_geojson"),
        actual_track,
    )
    return {
        "route": candidate_route,
        "metrics": candidate_metrics,
        "shipping_lane_reference": {
            "source": lane_reference.get("source"),
            "source_type": lane_reference.get("source_type"),
            "source_version": lane_reference.get("source_version"),
            "source_notes": lane_reference.get("source_notes"),
            "official": bool(lane_reference.get("official")),
        },
        "improvement": None,
    }


def compare_route_candidates(mmsi, route_prediction_id=None, route_version=None):
    normalized_mmsi = _normalize_mmsi(mmsi)
    history = get_route_prediction_history(normalized_mmsi)
    current_route = _select_route_prediction(
        history,
        route_prediction_id=route_prediction_id,
        route_version=route_version,
    )
    if not current_route:
        return {
            "status": "unavailable",
            "mmsi": normalized_mmsi,
            "current_route": None,
            "poc_lane_prior_candidate": None,
            "official_routeing_candidate": None,
            "actual_track": [],
            "current_metrics": None,
            "poc_candidate_metrics": None,
            "official_candidate_metrics": None,
            "poc_improvement": None,
            "official_improvement": None,
            "warnings": ["route_prediction_not_found"],
        }

    actual_track = _actual_track_for_prediction(normalized_mmsi, current_route)
    current_metrics = evaluate_actual_track_against_route(
        current_route.get("route_geojson"),
        actual_track,
    )
    poc_reference = load_poc_shipping_lane_reference()
    official_reference = load_official_routeing_reference()
    poc_candidate = _candidate_for_reference(
        current_route,
        actual_track,
        poc_reference,
        use_adapter=False,
    )
    official_candidate = _candidate_for_reference(
        current_route,
        actual_track,
        official_reference,
        use_adapter=True,
    )
    poc_candidate["improvement"] = _improvement(
        current_metrics,
        poc_candidate["metrics"],
    )
    official_candidate["improvement"] = _improvement(
        current_metrics,
        official_candidate["metrics"],
    )
    baseline_candidate_route = _route_for_candidate(
        "baseline",
        _baseline_route_result(current_route),
    )
    poc_candidate_route = _route_for_candidate(
        "poc_shipping_lane_prior",
        poc_candidate["route"],
    )
    ranked_candidates = rank_route_candidates(
        [
            baseline_candidate_route,
            poc_candidate_route,
        ],
        official_reference.get("features") or [],
    )
    official_ranked = ranked_candidates[0] if ranked_candidates else None
    official_ranked_route = (
        official_ranked.get("candidate")
        if official_ranked
        else baseline_candidate_route
    )
    official_ranked_metrics = evaluate_actual_track_against_route(
        official_ranked_route.get("estimated_route_geojson"),
        actual_track,
    )
    official_ranked_improvement = _improvement(
        current_metrics,
        official_ranked_metrics,
    )

    return {
        "status": "estimated",
        "mmsi": normalized_mmsi,
        "current_route": current_route,
        "lane_prior_candidate": official_candidate["route"],
        "poc_lane_prior_candidate": poc_candidate["route"],
        "official_routeing_candidate": official_candidate["route"],
        "official_ranked_candidate": official_ranked_route,
        "actual_track": actual_track,
        "current_metrics": current_metrics,
        "candidate_metrics": official_candidate["metrics"],
        "poc_candidate_metrics": poc_candidate["metrics"],
        "official_candidate_metrics": official_candidate["metrics"],
        "official_ranked_candidate_metrics": official_ranked_metrics,
        "improvement": official_candidate["improvement"],
        "poc_improvement": poc_candidate["improvement"],
        "official_improvement": official_candidate["improvement"],
        "official_ranked_improvement": official_ranked_improvement,
        "routeing_scores": {
            item["candidate_id"]: item["routeing_score"]
            for item in ranked_candidates
        },
        "ranked_candidates": ranked_candidates,
        "poc_shipping_lane_reference": poc_candidate["shipping_lane_reference"],
        "official_shipping_lane_reference": official_candidate[
            "shipping_lane_reference"
        ],
        "shipping_lane_reference": official_candidate["shipping_lane_reference"],
        "warnings": official_candidate["route"].get("warnings") or [],
    }

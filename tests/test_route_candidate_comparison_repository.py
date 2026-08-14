from unittest.mock import patch

from risk_monitor import route_candidate_comparison_repository


BASELINE_ROUTE = {
    "type": "LineString",
    "coordinates": [
        [0, 0],
        [10, 0],
    ],
}

CANDIDATE_ROUTE = {
    "type": "LineString",
    "coordinates": [
        [0, 0],
        [10, 1],
    ],
}


def _route():
    return {
        "route_prediction_id": "route-1",
        "mmsi": "228397600",
        "route_version": 1,
        "route_method": "land_avoidance_baseline",
        "distance_method": "navigable_route_baseline",
        "route_geojson": BASELINE_ROUTE,
        "great_circle_distance_nm": 600,
        "navigable_distance_nm": 600,
        "route_distance_ratio": 1,
        "origin_position_id": 100,
        "route_created_at": "2026-08-14T00:00:00+00:00",
        "status": "active",
    }


def _point(position_id, latitude, longitude):
    return {
        "position_id": position_id,
        "latitude": latitude,
        "longitude": longitude,
        "observed_at": f"2026-08-14T00:{position_id}:00+00:00",
    }


def _patch_common(actual_track=None, candidate_route=None):
    lane_reference = {
        "source": "test",
        "source_version": "v1",
        "source_notes": "test",
        "features": [],
    }
    candidate = {
        "status": "estimated",
        "route_method": "shipping_lane_prior_baseline",
        "estimated_route_geojson": candidate_route or CANDIDATE_ROUTE,
        "warnings": [],
    }
    return patch.multiple(
        route_candidate_comparison_repository,
        get_route_prediction_history=lambda _mmsi: [_route()],
        _actual_track_for_prediction=lambda *_args, **_kwargs: actual_track or [],
        load_official_routeing_reference=lambda: {
            **lane_reference,
            "official": True,
        },
        load_poc_shipping_lane_reference=lambda: {
            **lane_reference,
            "official": False,
        },
        adapt_routeing_features_for_prior=lambda features: features,
        apply_shipping_lane_prior=lambda *_args, **_kwargs: candidate,
    )


def test_candidate_evaluation_no_actual_ais():
    with _patch_common(actual_track=[]):
        result = route_candidate_comparison_repository.compare_route_candidates(
            "228397600"
        )

    assert result["current_metrics"]["status"] == "awaiting_data"
    assert result["candidate_metrics"]["status"] == "awaiting_data"


def test_candidate_better():
    actual_track = [
        _point(101, 1, 5),
        _point(102, 1, 6),
    ]
    with _patch_common(actual_track=actual_track):
        result = route_candidate_comparison_repository.compare_route_candidates(
            "228397600"
        )

    assert result["improvement"]["mean_deviation_improvement_nm"] > 0
    assert result["improvement"]["candidate_performs_better"] is True
    assert result["official_ranked_candidate_metrics"]["observation_count"] == 2


def test_candidate_worse():
    actual_track = [
        _point(101, 0, 5),
        _point(102, 0, 6),
    ]
    with _patch_common(actual_track=actual_track):
        result = route_candidate_comparison_repository.compare_route_candidates(
            "228397600"
        )

    assert result["improvement"]["mean_deviation_improvement_nm"] < 0
    assert result["improvement"]["candidate_performs_better"] is False
    assert result["official_ranked_candidate"] is not None


def test_missing_route_history():
    with patch.object(
        route_candidate_comparison_repository,
        "get_route_prediction_history",
        return_value=[],
    ):
        result = route_candidate_comparison_repository.compare_route_candidates(
            "228397600"
        )

    assert result["status"] == "unavailable"


def test_no_future_ais_leakage_uses_prediction_window():
    captured = {}

    def actual_track_for_prediction(_mmsi, route):
        captured["origin_position_id"] = route.get("origin_position_id")
        captured["superseded_at"] = route.get("superseded_at")
        return []

    with patch.multiple(
        route_candidate_comparison_repository,
        get_route_prediction_history=lambda _mmsi: [_route()],
        _actual_track_for_prediction=actual_track_for_prediction,
        load_official_routeing_reference=lambda: {
            "source": "test",
            "source_version": "v1",
            "features": [],
        },
        load_poc_shipping_lane_reference=lambda: {
            "source": "poc",
            "source_version": "v1",
            "features": [],
        },
        adapt_routeing_features_for_prior=lambda features: features,
        apply_shipping_lane_prior=lambda baseline, **_kwargs: baseline,
    ):
        route_candidate_comparison_repository.compare_route_candidates("228397600")

    assert captured["origin_position_id"] == 100


if __name__ == "__main__":
    test_candidate_evaluation_no_actual_ais()
    test_candidate_better()
    test_candidate_worse()
    test_missing_route_history()
    test_no_future_ais_leakage_uses_prediction_window()
    print("test_route_candidate_comparison_repository.py passed")

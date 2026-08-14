from risk_monitor.navigation.route_evaluation import (
    evaluate_actual_track_against_route,
)


ROUTE = {
    "type": "LineString",
    "coordinates": [
        [0, 0],
        [10, 0],
    ],
}


def _point(position_id, latitude, longitude):
    return {
        "position_id": position_id,
        "latitude": latitude,
        "longitude": longitude,
        "cog": 90,
        "sog": 12,
        "observed_at": f"2026-08-14T00:{position_id:02d}:00+00:00",
    }


def test_no_actual_ais_after_prediction():
    result = evaluate_actual_track_against_route(ROUTE, [])

    assert result["status"] == "awaiting_data"
    assert result["observation_count"] == 0


def test_one_actual_point_is_insufficient_but_measured():
    result = evaluate_actual_track_against_route(ROUTE, [_point(1, 0, 5)])

    assert result["status"] == "insufficient_data"
    assert result["observation_count"] == 1
    assert result["mean_deviation_nm"] == 0


def test_multiple_points_near_route_follow_prediction():
    result = evaluate_actual_track_against_route(
        ROUTE,
        [
            _point(1, 0, 2),
            _point(2, 0.02, 4),
            _point(3, 0.03, 6),
        ],
    )

    assert result["status"] == "following_prediction"
    assert result["route_adherence_ratio"] == 1


def test_multiple_points_far_from_route_deviate():
    result = evaluate_actual_track_against_route(
        ROUTE,
        [
            _point(1, 0.3, 2),
            _point(2, 0.4, 4),
            _point(3, 0.5, 6),
        ],
    )

    assert result["status"] == "deviating"
    assert result["route_adherence_ratio"] == 0


def test_mean_median_p90_and_max_deviation():
    result = evaluate_actual_track_against_route(
        ROUTE,
        [
            _point(1, 0, 1),
            _point(2, 0.1, 2),
            _point(3, 0.2, 3),
            _point(4, 0.3, 4),
        ],
    )

    assert round(result["mean_deviation_nm"], 1) == 9.0
    assert round(result["median_deviation_nm"], 1) == 9.0
    assert round(result["p90_deviation_nm"], 1) == 16.2
    assert round(result["max_deviation_nm"], 1) == 18.0


def test_route_progress_ratio():
    result = evaluate_actual_track_against_route(
        ROUTE,
        [
            _point(1, 0, 4),
        ],
    )

    assert 0.39 < result["route_progress_ratio"] < 0.41


def test_malformed_route():
    result = evaluate_actual_track_against_route(
        {
            "type": "Point",
            "coordinates": [0, 0],
        },
        [_point(1, 0, 1)],
    )

    assert result["status"] == "unavailable"
    assert "missing_or_malformed_route" in result["reasons"]


if __name__ == "__main__":
    test_no_actual_ais_after_prediction()
    test_one_actual_point_is_insufficient_but_measured()
    test_multiple_points_near_route_follow_prediction()
    test_multiple_points_far_from_route_deviate()
    test_mean_median_p90_and_max_deviation()
    test_route_progress_ratio()
    test_malformed_route()
    print("test_route_evaluation.py passed")

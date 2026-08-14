from risk_monitor.navigation.route_monitor import (
    calculate_bearing_difference_deg,
    calculate_distance_to_route,
    calculate_route_bearing_near_position,
    evaluate_route_deviation,
)


EASTBOUND_ROUTE = {
    "type": "LineString",
    "coordinates": [
        [0, 0],
        [10, 0],
    ],
}


def _position(latitude, longitude, cog=90):
    return {
        "latitude": latitude,
        "longitude": longitude,
        "cog": cog,
    }


def test_vessel_exactly_on_route():
    result = evaluate_route_deviation(
        _position(0, 5),
        90,
        EASTBOUND_ROUTE,
    )

    assert result["status"] == "on_route"
    assert result["distance_to_route_nm"] == 0
    assert result["recalculation_recommended"] is False


def test_small_deviation_stays_on_route():
    result = evaluate_route_deviation(
        _position(0.05, 5),
        90,
        EASTBOUND_ROUTE,
    )

    assert result["status"] == "on_route"
    assert 2 < result["distance_to_route_nm"] < 4


def test_large_distance_deviation():
    result = evaluate_route_deviation(
        _position(0.3, 5),
        90,
        EASTBOUND_ROUTE,
    )

    assert result["status"] == "deviating"
    assert result["distance_deviation"] is True
    assert result["recalculation_recommended"] is False


def test_large_course_deviation():
    result = evaluate_route_deviation(
        _position(0, 5, cog=180),
        180,
        EASTBOUND_ROUTE,
    )

    assert result["status"] == "deviating"
    assert result["course_deviation"] is True
    assert result["course_difference_deg"] == 90


def test_single_abnormal_point_does_not_trigger_reroute():
    result = evaluate_route_deviation(
        _position(0.3, 5),
        90,
        EASTBOUND_ROUTE,
        recent_positions=[
            _position(0, 3),
            _position(0, 4),
        ],
    )

    assert result["status"] == "deviating"
    assert result["consecutive_deviation_points"] == 1
    assert result["recalculation_recommended"] is False


def test_consecutive_deviation_points_trigger_reroute():
    result = evaluate_route_deviation(
        _position(0.5, 5),
        90,
        EASTBOUND_ROUTE,
        recent_positions=[
            _position(0.3, 3),
            _position(0.4, 4),
        ],
    )

    assert result["status"] == "deviating"
    assert result["consecutive_deviation_points"] == 3
    assert result["recalculation_recommended"] is True


def test_missing_cog_keeps_course_unavailable():
    result = evaluate_route_deviation(
        _position(0, 5, cog=None),
        None,
        EASTBOUND_ROUTE,
    )

    assert result["status"] == "on_route"
    assert result["course_difference_deg"] is None
    assert "missing_cog" in result["reasons"]


def test_no_route_is_unavailable():
    result = evaluate_route_deviation(
        _position(0, 5),
        90,
        None,
    )

    assert result["status"] == "unavailable"
    assert "missing_or_malformed_route" in result["reasons"]


def test_malformed_route_is_unavailable():
    result = evaluate_route_deviation(
        _position(0, 5),
        90,
        {
            "type": "Point",
            "coordinates": [0, 0],
        },
    )

    assert result["status"] == "unavailable"
    assert result["distance_to_route_nm"] is None


def test_bearing_wraparound_359_vs_1():
    assert calculate_bearing_difference_deg(359, 1) == 2


def test_distance_and_bearing_helpers():
    distance = calculate_distance_to_route(
        _position(0.1, 5),
        EASTBOUND_ROUTE,
    )
    bearing = calculate_route_bearing_near_position(
        _position(0.1, 5),
        EASTBOUND_ROUTE,
    )

    assert 5 < distance < 7
    assert bearing == 90


if __name__ == "__main__":
    test_vessel_exactly_on_route()
    test_small_deviation_stays_on_route()
    test_large_distance_deviation()
    test_large_course_deviation()
    test_single_abnormal_point_does_not_trigger_reroute()
    test_consecutive_deviation_points_trigger_reroute()
    test_missing_cog_keeps_course_unavailable()
    test_no_route_is_unavailable()
    test_malformed_route_is_unavailable()
    test_bearing_wraparound_359_vs_1()
    test_distance_and_bearing_helpers()
    print("test_route_monitor.py passed")

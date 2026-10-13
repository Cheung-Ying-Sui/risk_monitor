import pytest

from risk_monitor.navigation.route_progress import calculate_route_progress


def test_remaining_distance_follows_route_not_direct_destination_distance():
    route = {
        "type": "LineString",
        "coordinates": [[0, 0], [0, 10], [10, 10]],
    }

    result = calculate_route_progress(
        {"latitude": 5, "longitude": 0},
        route,
    )

    assert 888 < result["remaining_distance_nm"] < 894
    assert result["remaining_route_geojson"]["coordinates"][0] == pytest.approx(
        [0, 5]
    )
    assert result["remaining_route_geojson"]["coordinates"][-1] == [10, 10]


def test_remaining_distance_decreases_along_same_route():
    route = {
        "type": "LineString",
        "coordinates": [[0, 0], [10, 0]],
    }

    earlier = calculate_route_progress(
        {"latitude": 0, "longitude": 2}, route
    )
    later = calculate_route_progress(
        {"latitude": 0, "longitude": 8}, route
    )

    assert earlier["remaining_distance_nm"] > later["remaining_distance_nm"]
    assert earlier["remaining_distance_nm"] == pytest.approx(
        later["remaining_distance_nm"] * 4,
        rel=0.01,
    )

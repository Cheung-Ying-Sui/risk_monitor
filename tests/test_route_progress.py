import pytest

from risk_monitor.navigation.route_progress import calculate_route_progress


ROUTE = {
    "type": "LineString",
    "coordinates": [[0, 0], [5, 0], [10, 0]],
}


def test_route_progress_projects_position_onto_route():
    result = calculate_route_progress(
        {"latitude": 1, "longitude": 5},
        ROUTE,
    )

    assert result["route_progress"] == pytest.approx(0.5, abs=0.001)
    assert 59 < result["cross_track_error_nm"] < 61
    assert result["projected_position"]["longitude"] == pytest.approx(5)
    assert result["projected_position"]["latitude"] == pytest.approx(0)


def test_route_progress_is_clamped_to_route_start():
    result = calculate_route_progress(
        {"latitude": 0, "longitude": -2},
        ROUTE,
    )

    assert result["route_progress"] == 0
    assert result["projected_position"] == {"longitude": 0, "latitude": 0}


def test_route_progress_is_clamped_to_route_end():
    result = calculate_route_progress(
        {"latitude": 0, "longitude": 12},
        ROUTE,
    )

    assert result["route_progress"] == 1
    assert result["remaining_distance_nm"] == pytest.approx(0)
    assert len(result["remaining_route_geojson"]["coordinates"]) == 2


def test_antimeridian_route_uses_short_wrapped_segment():
    result = calculate_route_progress(
        {"latitude": 0, "longitude": 180},
        {"type": "LineString", "coordinates": [[179, 0], [-179, 0]]},
    )

    assert result["route_progress"] == pytest.approx(0.5, abs=0.001)
    assert result["cross_track_error_nm"] == pytest.approx(0, abs=0.001)


@pytest.mark.parametrize(
    "route",
    [
        None,
        {"type": "Point", "coordinates": [0, 0]},
        {"type": "LineString", "coordinates": [[0, 0]]},
        {"type": "LineString", "coordinates": [[0, 0], [0, 0]]},
    ],
)
def test_invalid_route_is_rejected(route):
    with pytest.raises(ValueError):
        calculate_route_progress({"latitude": 0, "longitude": 0}, route)

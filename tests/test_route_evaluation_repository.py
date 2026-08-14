from unittest.mock import patch

from risk_monitor import route_evaluation_repository


ROUTE = {
    "type": "LineString",
    "coordinates": [
        [0, 0],
        [10, 0],
    ],
}

ROUTE_V2 = {
    "type": "LineString",
    "coordinates": [
        [10, 0],
        [20, 0],
    ],
}


def _route(version=1, status="active"):
    return {
        "route_prediction_id": f"route-{version}",
        "vessel_id": "vessel-1",
        "mmsi": "228397600",
        "origin_position_id": version * 100,
        "destination_raw": "MAPTM",
        "destination_normalized": "Tanger Med",
        "destination_unlocode": "MAPTM",
        "route_version": version,
        "route_method": "direct_sea_baseline",
        "route_geojson": ROUTE if version == 1 else ROUTE_V2,
        "great_circle_distance_nm": 600,
        "navigable_distance_nm": 600,
        "route_distance_ratio": 1,
        "route_created_at": f"2026-08-14T0{version}:00:00+00:00",
        "route_update_reason": "initial_route" if version == 1 else "route_deviation",
        "status": status,
        "superseded_at": (
            "2026-08-14T02:00:00+00:00" if status == "superseded" else None
        ),
    }


def _point(position_id, latitude, longitude):
    return {
        "position_id": position_id,
        "latitude": latitude,
        "longitude": longitude,
        "cog": 90,
        "sog": 12,
        "observed_at": f"2026-08-14T02:{position_id:02d}:00+00:00",
    }


def test_missing_history():
    with patch.object(
        route_evaluation_repository,
        "get_route_prediction_history",
        return_value=[],
    ):
        result = route_evaluation_repository.evaluate_route_prediction("228397600")

    assert result["status"] == "unavailable"
    assert "route_prediction_not_found" in result["reasons"]


def test_active_route_evaluation():
    route = _route(version=1, status="active")
    with patch.object(
        route_evaluation_repository,
        "get_route_prediction_history",
        return_value=[route],
    ), patch.object(
        route_evaluation_repository,
        "get_track_points_after_prediction",
        return_value=[_point(101, 0, 5), _point(102, 0, 6)],
    ):
        result = route_evaluation_repository.evaluate_route_prediction("228397600")

    assert result["status"] == "following_prediction"
    assert result["route_version"] == 1
    assert result["observation_count"] == 2


def test_superseded_route_evaluation():
    route = _route(version=1, status="superseded")
    with patch.object(
        route_evaluation_repository,
        "get_route_prediction_history",
        return_value=[route],
    ), patch.object(
        route_evaluation_repository,
        "get_track_points_after_prediction",
        return_value=[_point(101, 0, 5), _point(102, 0, 6)],
    ):
        result = route_evaluation_repository.evaluate_route_prediction(
            "228397600",
            route_version=1,
        )

    assert result["status"] == "superseded"
    assert result["route_following_status"] == "following_prediction"


def test_v1_v2_independently_evaluated():
    v1 = _route(version=1, status="superseded")
    v2 = _route(version=2, status="active")

    def points_for_route(_mmsi, origin_position_id=None, **_kwargs):
        if origin_position_id == 100:
            return [_point(101, 0, 5), _point(102, 0, 6)]
        return [_point(201, 0, 15), _point(202, 0, 16)]

    with patch.object(
        route_evaluation_repository,
        "get_route_prediction_history",
        return_value=[v1, v2],
    ), patch.object(
        route_evaluation_repository,
        "get_track_points_after_prediction",
        side_effect=points_for_route,
    ):
        result_v1 = route_evaluation_repository.evaluate_route_prediction(
            "228397600",
            route_version=1,
        )
        result_v2 = route_evaluation_repository.evaluate_route_prediction(
            "228397600",
            route_version=2,
        )

    assert result_v1["route_version"] == 1
    assert result_v1["status"] == "superseded"
    assert result_v2["route_version"] == 2
    assert result_v2["status"] == "following_prediction"


if __name__ == "__main__":
    test_missing_history()
    test_active_route_evaluation()
    test_superseded_route_evaluation()
    test_v1_v2_independently_evaluated()
    print("test_route_evaluation_repository.py passed")

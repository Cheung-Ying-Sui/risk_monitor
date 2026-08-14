from pathlib import Path
from tempfile import TemporaryDirectory

from risk_monitor.navigation.route_prior import apply_shipping_lane_prior


BASELINE = {
    "status": "estimated",
    "route_method": "land_avoidance_baseline",
    "estimated_route_geojson": {
        "type": "LineString",
        "coordinates": [
            [0, 0],
            [10, 0],
        ],
    },
    "great_circle_distance_nm": 600,
    "navigable_distance_nm": 600,
    "route_distance_ratio": 1,
    "warnings": [],
}

LANE = {
    "id": "lane-1",
    "name": "Test lane",
    "type": "recommended_track",
    "source": "test",
    "bbox": {
        "min_lat": -1,
        "max_lat": 1,
        "min_lon": 0,
        "max_lon": 10,
    },
    "geometry": {
        "type": "LineString",
        "coordinates": [
            [2, 0],
            [5, 0],
            [8, 0],
        ],
    },
}


def _land_mask_file(geometries):
    directory = TemporaryDirectory()
    path = Path(directory.name) / "land_mask.json"
    path.write_text(
        "{\"type\":\"FeatureCollection\",\"features\":[]}",
        encoding="utf-8",
    )
    return directory, path


def test_no_lane_data_falls_back():
    result = apply_shipping_lane_prior(BASELINE, lane_features=[])

    assert result["shipping_lane_prior_applied"] is False
    assert result["route_method"] == "land_avoidance_baseline"


def test_route_outside_lane_region_falls_back():
    lane = {
        **LANE,
        "bbox": {
            "min_lat": 50,
            "max_lat": 51,
            "min_lon": 50,
            "max_lon": 51,
        },
    }

    result = apply_shipping_lane_prior(BASELINE, lane_features=[lane])

    assert result["shipping_lane_prior_applied"] is False


def test_route_intersects_region_and_candidate_follows_lane():
    temp_dir, path = _land_mask_file([])
    try:
        result = apply_shipping_lane_prior(
            BASELINE,
            lane_features=[LANE],
            land_mask_path=path,
        )
    finally:
        temp_dir.cleanup()

    assert result["route_method"] == "shipping_lane_prior_baseline"
    assert result["shipping_lane_prior_applied"] is True
    assert [5, 0] in result["estimated_route_geojson"]["coordinates"]


def test_invalid_lane_data_falls_back():
    lane = {
        **LANE,
        "geometry": {
            "type": "Point",
            "coordinates": [0, 0],
        },
    }

    result = apply_shipping_lane_prior(BASELINE, lane_features=[lane])

    assert result["shipping_lane_prior_applied"] is False


def test_candidate_excessive_detour_fallback():
    short_baseline = {
        **BASELINE,
        "navigable_distance_nm": 100,
    }
    temp_dir, path = _land_mask_file([])
    try:
        result = apply_shipping_lane_prior(
            short_baseline,
            lane_features=[LANE],
            land_mask_path=path,
        )
    finally:
        temp_dir.cleanup()

    assert result["shipping_lane_prior_applied"] is False
    assert "candidate_excessive_detour" in result["warnings"]


def test_current_baseline_preserved():
    result = apply_shipping_lane_prior(BASELINE, lane_features=[])

    assert result["estimated_route_geojson"] == BASELINE["estimated_route_geojson"]


def test_malformed_geojson_fallback():
    result = apply_shipping_lane_prior(
        {
            **BASELINE,
            "estimated_route_geojson": {
                "type": "Point",
                "coordinates": [0, 0],
            },
        },
        lane_features=[LANE],
    )

    assert "malformed_baseline_route" in result["warnings"]


def test_candidate_avoids_land_with_empty_mask():
    temp_dir, path = _land_mask_file([])
    try:
        result = apply_shipping_lane_prior(
            BASELINE,
            lane_features=[LANE],
            land_mask_path=path,
        )
    finally:
        temp_dir.cleanup()

    assert result["shipping_lane_prior_applied"] is True


if __name__ == "__main__":
    test_no_lane_data_falls_back()
    test_route_outside_lane_region_falls_back()
    test_route_intersects_region_and_candidate_follows_lane()
    test_invalid_lane_data_falls_back()
    test_candidate_excessive_detour_fallback()
    test_current_baseline_preserved()
    test_malformed_geojson_fallback()
    test_candidate_avoids_land_with_empty_mask()
    print("test_route_prior.py passed")

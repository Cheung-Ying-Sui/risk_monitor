import json
from pathlib import Path
from tempfile import TemporaryDirectory

from risk_monitor.navigation.route_engine import estimate_navigable_route


def _land_mask_file(geometries):
    directory = TemporaryDirectory()
    path = Path(directory.name) / "land_mask.json"
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {},
                        "geometry": geometry,
                    }
                    for geometry in geometries
                ],
            }
        ),
        encoding="utf-8",
    )
    return directory, path


def test_direct_sea_route():
    temp_dir, path = _land_mask_file([])
    try:
        result = estimate_navigable_route(
            0,
            0,
            0,
            10,
            land_mask_path=path,
        )
    finally:
        temp_dir.cleanup()

    assert result["status"] == "estimated"
    assert result["route_method"] == "direct_sea_baseline"
    assert result["distance_method"] == "navigable_route_baseline"


def test_route_crossing_land():
    temp_dir, path = _land_mask_file(
        [
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        [4, -1],
                        [6, -1],
                        [6, 1],
                        [4, 1],
                        [4, -1],
                    ]
                ],
            }
        ]
    )
    try:
        result = estimate_navigable_route(
            0,
            0,
            0,
            10,
            land_mask_path=path,
        )
    finally:
        temp_dir.cleanup()

    assert result["route_method"] == "land_avoidance_baseline"


def test_land_avoidance():
    temp_dir, path = _land_mask_file(
        [
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        [4, -1],
                        [6, -1],
                        [6, 1],
                        [4, 1],
                        [4, -1],
                    ]
                ],
            }
        ]
    )
    try:
        result = estimate_navigable_route(
            0,
            0,
            0,
            10,
            land_mask_path=path,
        )
    finally:
        temp_dir.cleanup()

    assert result["status"] == "estimated"
    assert len(result["estimated_route_geojson"]["coordinates"]) > 2


def test_multipolygon_land_mask():
    temp_dir, path = _land_mask_file(
        [
            {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [4, -1],
                            [6, -1],
                            [6, 1],
                            [4, 1],
                            [4, -1],
                        ]
                    ]
                ],
            }
        ]
    )
    try:
        result = estimate_navigable_route(
            0,
            0,
            0,
            10,
            land_mask_path=path,
        )
    finally:
        temp_dir.cleanup()

    assert result["status"] == "estimated"


def test_route_failure_fallback():
    temp_dir, path = _land_mask_file(
        [
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-20, -20],
                        [20, -20],
                        [20, 20],
                        [-20, 20],
                        [-20, -20],
                    ]
                ],
            }
        ]
    )
    try:
        result = estimate_navigable_route(
            0,
            0,
            0,
            10,
            land_mask_path=path,
        )
    finally:
        temp_dir.cleanup()

    assert result["status"] == "unavailable"
    assert "navigable_route_unavailable" in result["warnings"]
    assert result["distance_method"] == "great_circle_baseline"


def test_route_distance_greater_than_great_circle():
    temp_dir, path = _land_mask_file(
        [
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        [4, -1],
                        [6, -1],
                        [6, 1],
                        [4, 1],
                        [4, -1],
                    ]
                ],
            }
        ]
    )
    try:
        result = estimate_navigable_route(
            0,
            0,
            0,
            10,
            land_mask_path=path,
        )
    finally:
        temp_dir.cleanup()

    assert result["navigable_distance_nm"] > result["great_circle_distance_nm"]


def test_route_geojson_serialization():
    temp_dir, path = _land_mask_file([])
    try:
        result = estimate_navigable_route(
            1,
            2,
            3,
            4,
            land_mask_path=path,
        )
    finally:
        temp_dir.cleanup()

    assert result["estimated_route_geojson"]["type"] == "LineString"
    assert result["estimated_route_geojson"]["coordinates"][0] == [2.0, 1.0]


if __name__ == "__main__":
    test_direct_sea_route()
    test_route_crossing_land()
    test_land_avoidance()
    test_multipolygon_land_mask()
    test_route_failure_fallback()
    test_route_distance_greater_than_great_circle()
    test_route_geojson_serialization()
    print("test_route_engine.py passed")

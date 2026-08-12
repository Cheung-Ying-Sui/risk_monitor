from shapely.geometry import GeometryCollection, MultiPolygon, Point, Polygon, shape

from risk_zones.geojson_loader import build_iho_indexes, load_geojson, load_iho_seas
from risk_zones.geometry_builder import (
    GeometryBuildError,
    build_boundary_polygon,
    build_maritime_zone_geometry,
    match_iho_water_body,
    normalize_polygonal_geometry,
)
from risk_zones.geometry_validator import (
    compare_geometry_with_baseline,
    validate_geometry_result,
)


IHO_PATH = "static/iho_seas.geojson"
BASELINE_PATH = "JWLA_033/JWLA_033_Risk_Seas_Merge_Layer.json"


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def assert_equal(left, right, message):
    if left != right:
        raise AssertionError(f"{message}: {left!r} != {right!r}")


def test_polygon_to_multipolygon():
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 0)])
    result = normalize_polygonal_geometry(polygon)
    assert_equal(result.geom_type, "MultiPolygon", "Polygon should normalize to MultiPolygon")


def test_multipolygon_preserved():
    multipolygon = MultiPolygon([
        Polygon([(0, 0), (1, 0), (1, 1), (0, 0)]),
        Polygon([(2, 2), (3, 2), (3, 3), (2, 2)]),
    ])
    result = normalize_polygonal_geometry(multipolygon)
    assert_equal(len(result.geoms), 2, "MultiPolygon components should be preserved")


def test_iho_matching():
    iho = load_iho_seas(IHO_PATH)
    indexes = build_iho_indexes(iho)

    by_id = match_iho_water_body({"name": "Something Else", "iho_id": "38"}, indexes)
    assert_true(by_id["matched"], "IHO ID exact match should succeed")
    assert_equal(by_id["match_method"], "iho_id_exact", "IHO ID match method")

    by_name = match_iho_water_body({"name": "Gulf of Aden"}, indexes)
    assert_true(by_name["matched"], "IHO name exact match should succeed")
    assert_equal(by_name["match_method"], "name_exact", "IHO name match method")

    unmatched = match_iho_water_body({"name": "Not A Real Sea", "iho_id": "NOPE"}, indexes)
    assert_true(not unmatched["matched"], "Unmatched IHO should be explicit")


def test_boundary_polygon_auto_closed():
    polygon = build_boundary_polygon([[[40, 10], [50, 10], [50, 20], [40, 20]]])
    coords = list(polygon.exterior.coords)
    assert_equal(coords[0], coords[-1], "Boundary polygon should be auto-closed")


def test_iho_only_build():
    iho = load_iho_seas(IHO_PATH)
    result = build_maritime_zone_geometry(
        {
            "zone_name": "Gulf of Aden",
            "zone_type": "maritime",
            "named_water_bodies": [{"name": "Gulf of Aden", "iho_id": "38"}],
            "exclude_12nm_coastal_waters": False,
        },
        iho,
    )
    assert_equal(result["geometry"].geom_type, "MultiPolygon", "IHO-only result type")
    assert_true(result["source_components"]["used_iho_union"], "IHO union should be used")


def test_boundary_only_build():
    iho = load_iho_seas(IHO_PATH)
    result = build_maritime_zone_geometry(
        {
            "zone_name": "Boundary Only",
            "zone_type": "maritime",
            "boundary_polygon": [[[40, 10], [41, 10], [41, 11], [40, 10]]],
        },
        iho,
    )
    assert_equal(result["geometry"].geom_type, "MultiPolygon", "Boundary-only result type")
    assert_true(result["needs_review"], "Boundary-only result should need review")


def test_iho_boundary_intersection():
    iho = load_iho_seas(IHO_PATH)
    result = build_maritime_zone_geometry(
        {
            "zone_name": "Gulf of Aden clipped",
            "zone_type": "maritime",
            "named_water_bodies": [{"name": "Gulf of Aden", "iho_id": "38"}],
            "boundary_polygon": [[[40, 5], [55, 5], [55, 15], [40, 15]]],
        },
        iho,
    )
    assert_equal(result["geometry"].geom_type, "MultiPolygon", "Intersection result type")
    assert_true(result["source_components"]["used_boundary_polygon"], "Boundary should be used")


def test_geometry_collection_extraction():
    collection = GeometryCollection([
        Point(0, 0),
        Polygon([(0, 0), (1, 0), (1, 1), (0, 0)]),
    ])
    result = normalize_polygonal_geometry(collection)
    assert_equal(result.geom_type, "MultiPolygon", "GeometryCollection polygon extraction")
    assert_equal(len(result.geoms), 1, "Only polygonal components should be retained")


def test_invalid_geometry_handling():
    try:
        build_boundary_polygon([[[0, 0], [1, 1], [2, 2]]])
    except GeometryBuildError:
        return
    raise AssertionError("Invalid zero-area boundary should raise GeometryBuildError")


def test_validator_and_regression_helper():
    iho = load_iho_seas(IHO_PATH)
    build_result = build_maritime_zone_geometry(
        {
            "zone_name": "Gulf of Aden",
            "zone_type": "maritime",
            "named_water_bodies": [{"name": "Gulf of Aden", "iho_id": "38"}],
        },
        iho,
    )
    validation = validate_geometry_result(build_result, llm_confidence=0.9)
    assert_equal(validation["summary"]["status"], "validated", "Validation status")
    assert_true(validation["geometry"]["area_sq_km"] > 0, "Geodesic area should be positive")

    baseline = load_geojson(BASELINE_PATH)
    baseline_geometry = normalize_polygonal_geometry(shape(baseline["geometries"][0]))
    comparison = compare_geometry_with_baseline(build_result["geometry"], baseline_geometry)
    assert_true("intersection_over_union" in comparison, "Regression comparison should return IoU")
    assert_true(
        comparison["polygon_part_count_baseline"] > 0,
        "Baseline should contain polygonal components",
    )


def main():
    test_polygon_to_multipolygon()
    test_multipolygon_preserved()
    test_iho_matching()
    test_boundary_polygon_auto_closed()
    test_iho_only_build()
    test_boundary_only_build()
    test_iho_boundary_intersection()
    test_geometry_collection_extraction()
    test_invalid_geometry_handling()
    test_validator_and_regression_helper()
    print("geometry builder smoke tests passed")


if __name__ == "__main__":
    main()

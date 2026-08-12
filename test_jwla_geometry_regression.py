from shapely.geometry import MultiPolygon, shape
from shapely.ops import unary_union

from risk_zones.anchor_resolver import (
    collect_pending_anchors,
    detect_anchor_conditions,
    load_anchor_overrides,
    normalize_anchor_name,
    resolve_boundary_anchors,
    resolve_country_border,
    resolve_country_coastline,
    resolve_manual_anchor,
)
from risk_zones.geojson_loader import load_geojson, load_iho_seas
from risk_zones.geometry_builder import (
    GeometryBuildError,
    build_maritime_zone_geometry,
    normalize_polygonal_geometry,
)
from risk_zones.geometry_clipper import (
    clip_by_latitude,
    clip_by_longitude,
    clip_by_partial_conditions,
    evaluate_line_split,
)
from risk_zones.geometry_validator import (
    compare_geometry_with_baseline,
    geodesic_area_sq_km,
    validate_geometry_result,
)
from risk_zones.jwla_geometry_adapter import adapt_jwla_zone
from risk_zones.jwla_boundary_parser import (
    build_boundary_from_explicit_lines,
    extract_coordinate_pairs,
    parse_coordinate_component,
    parse_explicit_lines,
)


JWC_ZONES_PATH = "risk_zones/jwc_risk_zones.json"
IHO_PATH = "static/iho_seas.geojson"
BASELINE_PATH = "JWLA_033/JWLA_033_Risk_Seas_Merge_Layer.json"
COUNTRIES_PATH = "JWLA_033/JWLA_033_countries.json"
ANCHOR_OVERRIDES_PATH = "risk_zones/anchor_overrides.json"

AREA_CHANGE_THRESHOLD = 0.30
IOU_THRESHOLD = 0.80
SYMMETRIC_DIFFERENCE_THRESHOLD = 0.25


def summarize_input_structure(data):
    zones = data.get("zones") or []
    print("jwc_risk_zones.json structure")
    print(f"top_keys={sorted(data.keys())}")
    print(f"zone_count={len(zones)}")
    for zone in zones:
        components = zone.get("components") or {}
        named_water_bodies = components.get("named_water_bodies")
        explicit_lines = components.get("explicit_lines")
        print(
            "input_zone "
            f"name={zone.get('zone_name')!r} "
            f"zone_keys={sorted(zone.keys())} "
            f"component_keys={sorted(components.keys())} "
            f"named_water_bodies_count={len(named_water_bodies or [])} "
            f"explicit_lines_count={len(explicit_lines or [])} "
            f"has_jwc_boundary_polygon={'jwc_boundary_polygon' in components} "
            f"has_exclude_12nm={'exclude_12nm_coastal_waters' in components}"
        )


def build_all_zones(data, iho, countries, overrides):
    successful_geometries = []
    results = []

    for zone in data.get("zones") or []:
        adapted = adapt_jwla_zone(zone)
        anchor_resolution = resolve_boundary_anchors(
            adapted["boundary_conditions"]["anchor_conditions"],
            countries,
            overrides,
        )
        adapted["anchor_resolution"] = anchor_resolution
        result = {
            "zone_name": adapted["zone_name"],
            "adapter_warnings": adapted["adapter_warnings"],
            "geometry_generated": False,
            "build_method": None,
            "matched_iho_count": 0,
            "unmatched_iho_count": 0,
            "geometry_type": None,
            "area_sq_km": None,
            "parsed_coordinate_count": len(adapted["boundary_points_parsed"]),
            "partial_condition_count": len(adapted["boundary_conditions"]["partial_conditions"]),
            "boundary_polygon_generated": bool(adapted["boundary_polygon"]),
            "boundary_parser_confidence": adapted["boundary_parser_confidence"],
            "clipping_applied": False,
            "clipping_conditions": [],
            "detected_anchor_count": len(adapted["boundary_conditions"]["anchor_conditions"]),
            "resolved_anchor_count": anchor_resolution["resolved_count"],
            "ambiguous_anchor_count": anchor_resolution["ambiguous_count"],
            "manual_required_anchor_count": anchor_resolution["manual_required_count"],
            "unresolved_anchor_count": anchor_resolution["unresolved_count"],
            "anchor_statuses": [
                {
                    "raw_text": anchor["raw_text"],
                    "query_name": anchor["query_name"],
                    "anchor_type": anchor["anchor_type"],
                    "status": anchor["status"],
                    "resolution_method": anchor["resolution_method"],
                    "warnings": anchor["warnings"],
                }
                for anchor in anchor_resolution["anchors"]
            ],
            "warnings": [],
            "needs_review": False,
            "needs_review_reasons": [],
            "hard_fail_reasons": [],
        }

        try:
            build_result = build_maritime_zone_geometry(adapted, iho)
            validation = validate_geometry_result(build_result)
            successful_geometries.append(build_result["geometry"])

            matches = build_result.get("iho_matches") or []
            result.update(
                {
                    "geometry_generated": True,
                    "build_method": build_result["build_method"],
                    "matched_iho_count": sum(1 for match in matches if match.get("matched")),
                    "unmatched_iho_count": sum(
                        1 for match in matches if not match.get("matched")
                    ),
                    "geometry_type": build_result["geometry"].geom_type,
                    "area_sq_km": validation["geometry"]["area_sq_km"],
                    "warnings": build_result["warnings"],
                    "clipping_applied": build_result["clipping"]["clipping_applied"],
                    "clipping_conditions": build_result["clipping"]["clipping_conditions"],
                    "needs_review": validation["summary"]["status"] == "needs_review",
                    "needs_review_reasons": validation["review"]["needs_review_reasons"],
                    "hard_fail_reasons": validation["review"]["hard_fail_reasons"],
                }
            )
        except GeometryBuildError as exc:
            result["hard_fail_reasons"] = [str(exc)]
        except Exception as exc:
            result["hard_fail_reasons"] = [f"{type(exc).__name__}: {exc}"]

        results.append(result)
        print_zone_result(result)

    return results, successful_geometries


def print_zone_result(result):
    print(
        "zone_result "
        f"name={result['zone_name']!r} "
        f"build_method={result['build_method']} "
        f"matched_iho_count={result['matched_iho_count']} "
        f"unmatched_iho_count={result['unmatched_iho_count']} "
        f"parsed_coordinate_count={result['parsed_coordinate_count']} "
        f"partial_condition_count={result['partial_condition_count']} "
        f"boundary_polygon_generated={result['boundary_polygon_generated']} "
        f"boundary_parser_confidence={result['boundary_parser_confidence']} "
        f"clipping_applied={result['clipping_applied']} "
        f"clipping_conditions={result['clipping_conditions']} "
        f"detected_anchor_count={result['detected_anchor_count']} "
        f"resolved_anchor_count={result['resolved_anchor_count']} "
        f"ambiguous_anchor_count={result['ambiguous_anchor_count']} "
        f"manual_required_anchor_count={result['manual_required_anchor_count']} "
        f"unresolved_anchor_count={result['unresolved_anchor_count']} "
        f"anchor_statuses={result['anchor_statuses']} "
        f"geometry_generated={result['geometry_generated']} "
        f"geometry_type={result['geometry_type']} "
        f"area_sq_km={result['area_sq_km']} "
        f"adapter_warnings={result['adapter_warnings']} "
        f"warnings={result['warnings']} "
        f"needs_review={result['needs_review']} "
        f"needs_review_reasons={result['needs_review_reasons']} "
        f"hard_fail_reasons={result['hard_fail_reasons']}"
    )


def load_baseline_geometry():
    baseline = load_geojson(BASELINE_PATH)
    if baseline.get("type") == "GeometryCollection":
        geometries = [shape(item) for item in baseline.get("geometries") or []]
        return normalize_polygonal_geometry(unary_union(geometries))
    return normalize_polygonal_geometry(shape(baseline))


def bbox_difference(new_bounds, baseline_bounds):
    return {
        "min_lon_delta": new_bounds[0] - baseline_bounds[0],
        "min_lat_delta": new_bounds[1] - baseline_bounds[1],
        "max_lon_delta": new_bounds[2] - baseline_bounds[2],
        "max_lat_delta": new_bounds[3] - baseline_bounds[3],
    }


def run_regression(successful_geometries):
    if not successful_geometries:
        print("regression status=NEEDS_REVIEW reasons=['no_successful_geometries']")
        return {
            "status": "NEEDS_REVIEW",
            "reasons": ["no_successful_geometries"],
        }

    new_geometry = normalize_polygonal_geometry(unary_union(successful_geometries))
    baseline_geometry = load_baseline_geometry()
    comparison = compare_geometry_with_baseline(new_geometry, baseline_geometry)

    new_area = geodesic_area_sq_km(new_geometry)
    baseline_area = geodesic_area_sq_km(baseline_geometry)
    bbox_delta = bbox_difference(comparison["new_bounds"], comparison["baseline_bounds"])

    reasons = []
    if (
        comparison["area_change_ratio"] is not None
        and comparison["area_change_ratio"] > AREA_CHANGE_THRESHOLD
    ):
        reasons.append("area_change_ratio_gt_0.30")
    if (
        comparison["intersection_over_union"] is not None
        and comparison["intersection_over_union"] < IOU_THRESHOLD
    ):
        reasons.append("intersection_over_union_lt_0.80")
    if (
        comparison["symmetric_difference_ratio"] is not None
        and comparison["symmetric_difference_ratio"] > SYMMETRIC_DIFFERENCE_THRESHOLD
    ):
        reasons.append("symmetric_difference_ratio_gt_0.25")

    status = "NEEDS_REVIEW" if reasons else "PASS"
    print(
        "regression_metrics "
        f"new_total_area_sq_km={new_area} "
        f"baseline_area_sq_km={baseline_area} "
        f"area_change_ratio={comparison['area_change_ratio']} "
        f"intersection_over_union={comparison['intersection_over_union']} "
        f"symmetric_difference_ratio={comparison['symmetric_difference_ratio']} "
        f"polygon_part_count_new={comparison['polygon_part_count_new']} "
        f"polygon_part_count_baseline={comparison['polygon_part_count_baseline']} "
        f"new_bounds={comparison['new_bounds']} "
        f"baseline_bounds={comparison['baseline_bounds']} "
        f"bbox_difference={bbox_delta}"
    )
    print(f"regression status={status} reasons={reasons}")
    return {
        "status": status,
        "reasons": reasons,
        "metrics": comparison,
        "new_total_area_sq_km": new_area,
        "baseline_area_sq_km": baseline_area,
        "bbox_difference": bbox_delta,
    }


def run_boundary_parser_tests():
    assert parse_coordinate_component("25°19'15\"N")["value"] > 0
    assert parse_coordinate_component("13°30'S")["value"] < 0
    assert parse_coordinate_component("65°00'E")["value"] > 0
    assert parse_coordinate_component("3°00′W")["value"] < 0
    decimal_minutes = parse_coordinate_component("25°19.25'N")
    assert round(decimal_minutes["value"], 6) == round(25 + 19.25 / 60, 6)

    one_pair = extract_coordinate_pairs("point at 10°48’N, 65°E")
    assert len(one_pair) == 1
    assert one_pair[0]["lon"] == 65.0
    assert one_pair[0]["lat"] == 10.8

    many_pairs = extract_coordinate_pairs(
        "from 0°40′S, 3°00′E and then to 0°40′S, 8°42′E"
    )
    assert len(many_pairs) == 2

    lat_only = parse_explicit_lines(["south of Latitude 18°N"])
    assert lat_only["partial_conditions"][0]["type"] == "south_of_latitude"

    lon_only = parse_explicit_lines(["east of Longitude 65°E"])
    assert lon_only["partial_conditions"][0]["type"] == "east_of_longitude"

    assert parse_coordinate_component("not a coordinate") is None

    polygon = build_boundary_from_explicit_lines(
        [
            "from 0°00′N, 0°00′E to 0°00′N, 1°00′E",
            "then to 1°00′N, 1°00′E",
        ]
    )
    assert polygon["boundary_polygon"][0][0] == polygon["boundary_polygon"][0][-1]

    insufficient = build_boundary_from_explicit_lines(["from 0°00′N, 0°00′E"])
    assert insufficient["boundary_polygon"] is None


def run_clipper_tests():
    base = MultiPolygon([
        shape(
            {
                "type": "Polygon",
                "coordinates": [[[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]]],
            }
        ),
        shape(
            {
                "type": "Polygon",
                "coordinates": [[[2, -1], [4, -1], [4, 1], [2, 1], [2, -1]]],
            }
        ),
    ])
    assert not clip_by_latitude(base, 0, "north_of").is_empty
    assert not clip_by_latitude(base, 0, "south_of").is_empty
    assert not clip_by_longitude(base, 0, "east_of").is_empty
    assert not clip_by_longitude(base, 0, "west_of").is_empty

    multiple = clip_by_partial_conditions(
        base,
        [
            {"type": "north_of_latitude", "value": -0.5},
            {"type": "west_of_longitude", "value": 3},
        ],
    )
    assert multiple["applied_conditions"]
    assert normalize_polygonal_geometry(multiple["geometry"]).geom_type == "MultiPolygon"

    empty = clip_by_partial_conditions(
        base,
        [{"type": "north_of_latitude", "value": 99}],
    )
    assert empty["geometry"].is_empty

    unsafe = evaluate_line_split(
        base,
        [{"lon": 0, "lat": 0}, {"lon": 0.5, "lat": 0.5}],
    )
    assert unsafe["needs_review"]

    side_selection = evaluate_line_split(
        shape(
            {
                "type": "Polygon",
                "coordinates": [[[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]]],
            }
        ),
        [{"lon": -1, "lat": 0}, {"lon": 1, "lat": 0}],
        side_hint="north",
    )
    assert side_selection["needs_review"]

    coast_anchor_unavailable = build_boundary_from_explicit_lines(
        ["from coast of Togo 6°06′45″N, 1°12′E to 0°40′S, 3°00′E"]
    )
    assert "requires_coastline_geometry" in coast_anchor_unavailable["needs_review_reasons"]


def run_anchor_resolver_tests(countries, overrides):
    assert normalize_anchor_name("Cape Lopez Peninsula") == "cape_lopez_peninsula"

    border_conditions = detect_anchor_conditions("Ukraine-Romania border")
    assert border_conditions[0]["type"] == "country_border"

    coast_conditions = detect_anchor_conditions("from the coast of Togo 6°N")
    assert coast_conditions[0]["type"] == "country_coastline"

    bay_conditions = detect_anchor_conditions("from Mnazi Bay at 10°S")
    assert bay_conditions[0]["anchor_type"] == "bay"
    baia_conditions = detect_anchor_conditions("from Baía do Lúrio at 13°S")
    assert baia_conditions[0]["anchor_type"] == "bay"

    cape_conditions = detect_anchor_conditions("to Cape Lopez Peninsula, Gabon")
    assert any(condition["anchor_type"] == "peninsula" for condition in cape_conditions)

    coastline = resolve_country_coastline("Togo", countries)
    assert coastline["status"] in {"ambiguous", "unresolved"}

    missing = resolve_country_coastline("Atlantis", countries)
    assert missing["status"] == "unresolved"

    border = resolve_country_border("Ukraine", "Romania", countries)
    assert border["status"] in {"ambiguous", "unresolved"}

    multi_candidate = resolve_boundary_anchors(
        detect_anchor_conditions("Ukraine-Romania border"),
        countries,
        overrides,
    )
    assert multi_candidate["needs_review"]

    manual_missing = resolve_manual_anchor("Mnazi Bay", overrides)
    assert manual_missing["status"] == "manual_required"

    manual_test_overrides = {
        "anchors": {
            "mnazi_bay": {
                "canonical_name": "Mnazi Bay",
                "anchor_type": "bay",
                "longitude": 40.0,
                "latitude": -10.0,
                "country": "Testland",
                "source_name": "Test Source",
                "source_reference": "Unit test fixture",
                "verification_status": "manual_verified",
                "verified_at": "2026-08-12",
                "verified_by": "unit-test",
                "notes": "Synthetic test anchor.",
            }
        }
    }
    manual_resolved = resolve_manual_anchor("Mnazi Bay", manual_test_overrides)
    assert manual_resolved["status"] == "resolved"


def main():
    countries = load_geojson(COUNTRIES_PATH)
    overrides = load_anchor_overrides(ANCHOR_OVERRIDES_PATH)
    run_boundary_parser_tests()
    run_clipper_tests()
    run_anchor_resolver_tests(countries, overrides)
    data = load_geojson(JWC_ZONES_PATH)
    iho = load_iho_seas(IHO_PATH)

    summarize_input_structure(data)
    results, successful_geometries = build_all_zones(data, iho, countries, overrides)
    regression = run_regression(successful_geometries)

    generated_count = sum(1 for result in results if result["geometry_generated"])
    failed = [result["zone_name"] for result in results if not result["geometry_generated"]]
    print(
        "summary "
        f"total_zones={len(results)} "
        f"generated_count={generated_count} "
        f"failed_zones={failed} "
        f"regression_status={regression['status']}"
    )
    print(f"pending_anchors={collect_pending_anchors(results)}")


if __name__ == "__main__":
    main()

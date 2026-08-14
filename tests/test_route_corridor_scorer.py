from risk_monitor.navigation.route_corridor_scorer import (
    evaluate_route_corridor,
    rank_route_candidates,
)
from risk_monitor.navigation.routeing_feature_adapter import (
    adapt_routeing_features_for_prior,
)


ROUTE = {
    "type": "LineString",
    "coordinates": [
        [0, 0],
        [10, 0],
    ],
}

FAR_ROUTE = {
    "type": "LineString",
    "coordinates": [
        [0, 5],
        [10, 5],
    ],
}


def _area(feature_id, routeing_type, coordinates):
    return {
        "id": feature_id,
        "name": feature_id,
        "routeing_type": routeing_type,
        "geometry_kind": "area",
        "geometry": {
            "type": "Polygon",
            "coordinates": [coordinates],
        },
    }


def _line(feature_id, routeing_type, coordinates):
    return {
        "id": feature_id,
        "name": feature_id,
        "routeing_type": routeing_type,
        "geometry_kind": "line",
        "geometry": {
            "type": "LineString",
            "coordinates": coordinates,
        },
    }


def test_route_completely_outside_official_area():
    result = evaluate_route_corridor(
        FAR_ROUTE,
        [
            _area(
                "lane",
                "traffic_lane",
                [[0, -1], [10, -1], [10, 1], [0, 1], [0, -1]],
            )
        ],
    )

    assert result["traffic_lane_overlap_distance_nm"] == 0


def test_route_inside_traffic_lane():
    result = evaluate_route_corridor(
        ROUTE,
        [
            _area(
                "lane",
                "traffic_lane",
                [[0, -1], [10, -1], [10, 1], [0, 1], [0, -1]],
            )
        ],
    )

    assert result["traffic_lane_overlap_distance_nm"] > 500
    assert result["traffic_lane_score"] > 30


def test_route_partially_overlaps_traffic_lane():
    result = evaluate_route_corridor(
        ROUTE,
        [
            _area(
                "lane",
                "traffic_lane",
                [[0, -1], [5, -1], [5, 1], [0, 1], [0, -1]],
            )
        ],
    )

    assert 0.45 < result["official_area_overlap_ratio"] < 0.55


def test_recommended_track_proximity():
    result = evaluate_route_corridor(
        ROUTE,
        [
            _line(
                "recommended",
                "recommended_track",
                [[0, 0.05], [10, 0.05]],
            )
        ],
    )

    assert result["recommended_track_proximity_nm"] < 4
    assert result["recommended_track_score"] > 10


def test_precautionary_area_mild_penalty():
    clear = evaluate_route_corridor(ROUTE, [])
    precautionary = evaluate_route_corridor(
        ROUTE,
        [
            _area(
                "precautionary",
                "precautionary_area",
                [[0, -1], [10, -1], [10, 1], [0, 1], [0, -1]],
            )
        ],
    )

    assert precautionary["precautionary_area_distance_nm"] > 500
    assert precautionary["constraint_score"] < clear["constraint_score"]


def test_tss_boundary_crossing_recorded_and_penalized():
    result = evaluate_route_corridor(
        ROUTE,
        [
            _line(
                "boundary",
                "other",
                [[5, -1], [5, 1]],
            )
        ],
    )

    assert result["boundary_crossings"] == 1
    assert result["constraint_score"] == 5


def test_polygon_not_converted_to_centerline():
    adapted = adapt_routeing_features_for_prior(
        [
            _area(
                "lane",
                "traffic_lane",
                [[0, -1], [10, -1], [10, 1], [0, 1], [0, -1]],
            )
        ]
    )

    assert adapted == []


def test_candidate_ranking():
    candidates = [
        {
            "candidate_id": "outside",
            "estimated_route_geojson": FAR_ROUTE,
        },
        {
            "candidate_id": "inside",
            "estimated_route_geojson": ROUTE,
        },
    ]

    ranked = rank_route_candidates(
        candidates,
        [
            _area(
                "lane",
                "traffic_lane",
                [[0, -1], [10, -1], [10, 1], [0, 1], [0, -1]],
            )
        ],
    )

    assert ranked[0]["candidate_id"] == "inside"


def test_excessive_detour_penalty():
    direct = evaluate_route_corridor(ROUTE, [])
    detour = evaluate_route_corridor(
        {
            "type": "LineString",
            "coordinates": [[0, 0], [0, 5], [10, 5], [10, 0]],
        },
        [],
    )

    assert detour["distance_efficiency_score"] < direct["distance_efficiency_score"]


def test_no_routeing_data():
    result = evaluate_route_corridor(ROUTE, [])

    assert "no_routeing_data" in result["warnings"]
    assert result["routeing_score"] is not None


def test_malformed_geometry():
    result = evaluate_route_corridor(
        {
            "type": "Point",
            "coordinates": [0, 0],
        },
        [],
    )

    assert result["status"] == "unavailable"


def test_baseline_ranks_higher():
    ranked = rank_route_candidates(
        [
            {"candidate_id": "baseline", "estimated_route_geojson": ROUTE},
            {"candidate_id": "poc", "estimated_route_geojson": FAR_ROUTE},
        ],
        [
            _area(
                "lane",
                "traffic_lane",
                [[0, -1], [10, -1], [10, 1], [0, 1], [0, -1]],
            )
        ],
    )

    assert ranked[0]["candidate_id"] == "baseline"


def test_poc_ranks_higher():
    ranked = rank_route_candidates(
        [
            {"candidate_id": "baseline", "estimated_route_geojson": FAR_ROUTE},
            {"candidate_id": "poc", "estimated_route_geojson": ROUTE},
        ],
        [
            _area(
                "lane",
                "traffic_lane",
                [[0, -1], [10, -1], [10, 1], [0, 1], [0, -1]],
            )
        ],
    )

    assert ranked[0]["candidate_id"] == "poc"


if __name__ == "__main__":
    test_route_completely_outside_official_area()
    test_route_inside_traffic_lane()
    test_route_partially_overlaps_traffic_lane()
    test_recommended_track_proximity()
    test_precautionary_area_mild_penalty()
    test_tss_boundary_crossing_recorded_and_penalized()
    test_polygon_not_converted_to_centerline()
    test_candidate_ranking()
    test_excessive_detour_penalty()
    test_no_routeing_data()
    test_malformed_geometry()
    test_baseline_ranks_higher()
    test_poc_ranks_higher()
    print("test_route_corridor_scorer.py passed")

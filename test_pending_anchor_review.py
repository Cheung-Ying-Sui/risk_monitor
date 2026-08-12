from risk_zones.pending_anchor_review import (
    build_pending_anchor_review,
    make_review_id,
    suggested_action_for_anchor,
    validate_review_decision,
)


def sample_zone_results():
    candidate_line = {
        "type": "LineString",
        "coordinates": [[0, 0], [1, 1]],
    }
    return [
        {
            "zone_name": "Zone A",
            "anchor_statuses": [
                {
                    "raw_text": "Test Bay",
                    "query_name": "Test Bay",
                    "anchor_type": "named_anchor",
                    "status": "manual_required",
                    "geometry_type": None,
                    "geometry": None,
                    "resolution_method": "manual_override_missing",
                    "confidence": 0.0,
                    "source": None,
                    "warnings": ["manual_anchor_missing"],
                },
                {
                    "raw_text": "Test Bay",
                    "query_name": "Test Bay",
                    "anchor_type": "named_anchor",
                    "status": "manual_required",
                    "geometry_type": None,
                    "geometry": None,
                    "resolution_method": "manual_override_missing",
                    "confidence": 0.0,
                    "source": None,
                    "warnings": ["manual_anchor_missing"],
                },
                {
                    "raw_text": "Test Coast",
                    "query_name": "Testland",
                    "anchor_type": "country_coastline",
                    "status": "ambiguous",
                    "geometry_type": "LineString",
                    "geometry": candidate_line,
                    "resolution_method": "country_polygon_boundary",
                    "confidence": 0.4,
                    "source": "country_features",
                    "warnings": ["country_boundary_includes_land_borders_not_only_coastline"],
                },
                {
                    "raw_text": "A-B border",
                    "query_name": "A-B",
                    "anchor_type": "country_border",
                    "status": "unresolved",
                    "geometry_type": None,
                    "geometry": None,
                    "resolution_method": "country_name_not_found",
                    "confidence": 0.0,
                    "source": None,
                    "warnings": ["missing_country_feature:B"],
                },
            ],
        }
    ]


def test_review_id_deterministic():
    first = make_review_id("JWLA", "Zone A", "Test Bay", "named_anchor")
    second = make_review_id("JWLA", "Zone A", "Test Bay", "named_anchor")
    assert first == second


def test_actions():
    assert (
        suggested_action_for_anchor(
            {
                "status": "manual_required",
                "anchor_type": "named_anchor",
                "warnings": ["manual_anchor_missing"],
            }
        )
        == "manual_coordinate_verification"
    )
    assert (
        suggested_action_for_anchor(
            {"status": "ambiguous", "anchor_type": "country_coastline", "warnings": []}
        )
        == "resolve_with_coastline_gis"
    )
    assert (
        suggested_action_for_anchor(
            {"status": "unresolved", "anchor_type": "country_border", "warnings": []}
        )
        == "add_complete_country_boundary_data"
    )


def test_queue_building():
    queue = build_pending_anchor_review(sample_zone_results(), source_document="TEST_DOC")
    assert queue["pending_count"] == 3
    assert len(queue["items"]) == 3
    assert any(item["candidate_geometries"] for item in queue["items"])
    item = queue["items"][0]
    assert item["review"]["decision"] == "pending"
    assert item["review"]["longitude"] is None


def test_review_decision_validation():
    queue = build_pending_anchor_review(sample_zone_results(), source_document="TEST_DOC")
    item = queue["items"][0]
    assert validate_review_decision(item)["valid"]

    item["review"]["decision"] = "verified"
    invalid = validate_review_decision(item)
    assert not invalid["valid"]
    assert "longitude_required_for_verified" in invalid["errors"]

    item["review"].update(
        {
            "longitude": 10.0,
            "latitude": -5.0,
            "source_name": "Test Source",
            "source_reference": "Test Reference",
            "verified_by": "unit-test",
            "verified_at": "2026-08-12",
        }
    )
    assert validate_review_decision(item)["valid"]


def main():
    test_review_id_deterministic()
    test_actions()
    test_queue_building()
    test_review_decision_validation()
    print("pending anchor review tests passed")


if __name__ == "__main__":
    main()

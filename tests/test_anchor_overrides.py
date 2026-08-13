from risk_zones.anchor_override_validator import validate_anchor_override
from risk_zones.anchor_resolver import collect_pending_anchors, resolve_manual_anchor


def valid_anchor():
    return {
        "canonical_name": "TEST BAY",
        "anchor_type": "bay",
        "longitude": 10.0,
        "latitude": -5.0,
        "country": "Testland",
        "source_name": "Test Source",
        "source_reference": "Unit test fixture",
        "verification_status": "manual_verified",
        "verified_at": "2026-08-12",
        "verified_by": "unit-test",
        "notes": "Synthetic test anchor.",
        "aliases": ["TEST B."],
    }


def test_validator():
    assert validate_anchor_override(valid_anchor())["valid"]

    invalid_lon = {**valid_anchor(), "longitude": 999}
    assert "longitude_out_of_range" in validate_anchor_override(invalid_lon)["errors"]

    missing_source = {**valid_anchor(), "source_reference": ""}
    assert "source_reference_required" in validate_anchor_override(missing_source)["errors"]

    missing_verified_by = {**valid_anchor(), "verified_by": ""}
    assert "verified_by_required" in validate_anchor_override(missing_verified_by)["errors"]


def test_resolution():
    anchor = valid_anchor()
    overrides = {
        "anchors": {
            "test_bay": anchor,
            "test_b": {**anchor, "_matched_alias": "TEST B."},
        }
    }

    exact = resolve_manual_anchor("TEST BAY", overrides)
    assert exact["status"] == "resolved"
    assert exact["resolution_method"] == "manual_override_exact"
    assert exact["manual_verified"] is True
    assert exact["source"] == "Unit test fixture"

    alias = resolve_manual_anchor("TEST B.", overrides)
    assert alias["status"] == "resolved"
    assert alias["resolution_method"] == "manual_override_alias"

    unmatched = resolve_manual_anchor("UNKNOWN BAY", overrides)
    assert unmatched["status"] == "manual_required"


def test_invalid_anchor_excluded_pattern():
    invalid_anchor = {**valid_anchor(), "verified_by": ""}
    validation = validate_anchor_override(invalid_anchor)
    overrides = {"anchors": {} if not validation["valid"] else {"bad": invalid_anchor}}
    assert resolve_manual_anchor("TEST BAY", overrides)["status"] == "manual_required"


def test_pending_collection():
    pending = collect_pending_anchors(
        [
            {
                "zone_name": "Zone A",
                "anchor_statuses": [
                    {
                        "query_name": "TEST BAY",
                        "anchor_type": "bay",
                        "status": "manual_required",
                        "raw_text": "TEST BAY",
                        "warnings": ["manual_anchor_missing"],
                    },
                    {
                        "query_name": "TEST CAPE",
                        "anchor_type": "cape",
                        "status": "resolved",
                        "raw_text": "TEST CAPE",
                        "warnings": [],
                    },
                ],
            }
        ]
    )
    assert len(pending) == 1
    assert pending[0]["anchor_name"] == "TEST BAY"


def main():
    test_validator()
    test_resolution()
    test_invalid_anchor_excluded_pattern()
    test_pending_collection()
    print("anchor override tests passed")


if __name__ == "__main__":
    main()

from datetime import datetime, timezone

from risk_monitor.navigation.eta_engine import (
    calculate_great_circle_distance_nm,
    estimate_eta,
    estimate_sailing_speed,
)


CALCULATED_AT = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)
HONG_KONG_DESTINATION = {
    "raw_destination": "Hong Kong",
    "normalized_destination": "Hong Kong",
    "latitude": 22.3193,
    "longitude": 114.1694,
    "resolution_status": "resolved",
    "resolution_method": "port_name_exact",
    "confidence": "high",
}


def test_great_circle_distance():
    distance = calculate_great_circle_distance_nm(
        1.2644,
        103.84,
        22.3193,
        114.1694,
    )

    assert 1350 < distance < 1450


def test_recent_6h_speed():
    speed = estimate_sailing_speed(
        recent_6h_positions=[
            {"sog": 10},
            {"sog": 12},
            {"sog": 11},
        ],
        current_sog=7,
    )

    assert speed["estimated_speed_knots"] == 11
    assert speed["speed_method"] == "recent_6h_moving_sog_median"


def test_recent_24h_fallback():
    speed = estimate_sailing_speed(
        recent_6h_positions=[
            {"sog": 12},
        ],
        recent_24h_positions=[
            {"sog": 8},
            {"sog": 10},
            {"sog": 12},
        ],
    )

    assert speed["estimated_speed_knots"] == 10
    assert speed["speed_method"] == "recent_24h_moving_sog_median"


def test_current_sog_fallback():
    speed = estimate_sailing_speed(
        recent_6h_positions=[],
        recent_24h_positions=[],
        historical_positions=[],
        current_sog=13.4,
    )

    assert speed["estimated_speed_knots"] == 13.4
    assert speed["speed_method"] == "current_sog"


def test_no_valid_speed():
    speed = estimate_sailing_speed(
        recent_6h_positions=[
            {"sog": None},
            {"sog": -1},
            {"sog": 60},
        ],
        current_sog=None,
    )

    assert speed["estimated_speed_knots"] is None
    assert speed["speed_method"] == "unavailable"


def test_stopped_vessel():
    speed = estimate_sailing_speed(
        recent_6h_positions=[
            {"sog": 0},
            {"sog": 0.5},
        ],
        current_sog=0,
    )

    assert "vessel_stopped_or_very_low_sog" in speed["warnings"]


def test_eta_datetime_calculation():
    result = estimate_eta(
        {
            "mmsi": "123",
            "latitude": 1.2644,
            "longitude": 103.84,
            "destination": "Hong Kong",
            "sog": 20,
        },
        speed_context={
            "estimated_speed_knots": 20,
            "speed_method": "current_sog",
            "speed_sample_count": 1,
            "speed_variability": None,
            "warnings": [],
        },
        destination_resolution=HONG_KONG_DESTINATION,
        calculated_at=CALCULATED_AT,
    )

    assert result["status"] == "estimated"
    assert result["estimated_remaining_hours"] > 60
    assert result["baseline_estimated_eta"].startswith("2026-08-16")


def test_eta_v2_uses_navigable_route_distance():
    result = estimate_eta(
        {
            "mmsi": "123",
            "latitude": 1.2644,
            "longitude": 103.84,
            "destination": "Hong Kong",
        },
        speed_context={
            "estimated_speed_knots": 10,
            "speed_method": "recent_6h_moving_sog_median",
            "speed_sample_count": 3,
            "speed_variability": 1,
            "warnings": [],
        },
        destination_resolution=HONG_KONG_DESTINATION,
        route_result={
            "status": "estimated",
            "route_method": "land_avoidance_baseline",
            "distance_method": "navigable_route_baseline",
            "great_circle_distance_nm": 100,
            "navigable_distance_nm": 120,
            "route_distance_ratio": 1.2,
            "estimated_route_geojson": {
                "type": "LineString",
                "coordinates": [[103.84, 1.2644], [114.1694, 22.3193]],
            },
            "warnings": [],
        },
        calculated_at=CALCULATED_AT,
    )

    assert result["distance_method"] == "navigable_route_baseline"
    assert result["remaining_distance_nm"] == 120
    assert result["great_circle_distance_nm"] == 100
    assert result["estimated_remaining_hours"] == 12


def test_eta_route_failure_fallback():
    result = estimate_eta(
        {
            "mmsi": "123",
            "latitude": 1.2644,
            "longitude": 103.84,
            "destination": "Hong Kong",
        },
        speed_context={
            "estimated_speed_knots": 10,
            "speed_method": "recent_6h_moving_sog_median",
            "speed_sample_count": 3,
            "speed_variability": 1,
            "warnings": [],
        },
        destination_resolution=HONG_KONG_DESTINATION,
        route_result={
            "status": "unavailable",
            "route_method": "land_avoidance_baseline",
            "distance_method": "great_circle_baseline",
            "warnings": ["navigable_route_unavailable"],
        },
        calculated_at=CALCULATED_AT,
    )

    assert result["distance_method"] == "great_circle_baseline"
    assert "navigable_route_unavailable" in result["warnings"]


def test_ais_eta_comparison():
    result = estimate_eta(
        {
            "mmsi": "123",
            "latitude": 1.2644,
            "longitude": 103.84,
            "destination": "Hong Kong",
            "eta": "08-16 12:00",
            "sog": 20,
        },
        speed_context={
            "estimated_speed_knots": 20,
            "speed_method": "current_sog",
            "speed_sample_count": 1,
            "speed_variability": None,
            "warnings": [],
        },
        destination_resolution=HONG_KONG_DESTINATION,
        calculated_at=CALCULATED_AT,
    )

    assert result["reported_ais_eta"] == "2026-08-16T12:00:00+00:00"
    assert result["eta_difference_hours"] is not None


def test_confidence_high():
    result = estimate_eta(
        {
            "mmsi": "123",
            "latitude": 1.2644,
            "longitude": 103.84,
            "destination": "Hong Kong",
        },
        speed_context={
            "estimated_speed_knots": 18,
            "speed_method": "recent_6h_moving_sog_median",
            "speed_sample_count": 4,
            "speed_variability": 0.5,
            "warnings": [],
        },
        destination_resolution=HONG_KONG_DESTINATION,
        calculated_at=CALCULATED_AT,
    )

    assert result["confidence"] == "high"


def test_confidence_medium():
    result = estimate_eta(
        {
            "mmsi": "123",
            "latitude": 1.2644,
            "longitude": 103.84,
            "destination": "Hong Kong",
        },
        speed_context={
            "estimated_speed_knots": 18,
            "speed_method": "recent_24h_moving_sog_median",
            "speed_sample_count": 4,
            "speed_variability": 1.5,
            "warnings": [],
        },
        destination_resolution=HONG_KONG_DESTINATION,
        calculated_at=CALCULATED_AT,
    )

    assert result["confidence"] == "medium"


def test_confidence_low():
    result = estimate_eta(
        {
            "mmsi": "123",
            "latitude": 1.2644,
            "longitude": 103.84,
            "destination": "Hong Kong",
        },
        speed_context={
            "estimated_speed_knots": 18,
            "speed_method": "current_sog",
            "speed_sample_count": 1,
            "speed_variability": None,
            "warnings": [],
        },
        destination_resolution=HONG_KONG_DESTINATION,
        calculated_at=CALCULATED_AT,
    )

    assert result["confidence"] == "low"


def test_malformed_input():
    result = estimate_eta(
        {
            "mmsi": "123",
            "latitude": "bad",
            "longitude": 103.84,
            "destination": "Hong Kong",
            "eta": "not-a-date",
        },
        speed_context={
            "estimated_speed_knots": 18,
            "speed_method": "current_sog",
            "speed_sample_count": 1,
            "speed_variability": None,
            "warnings": [],
        },
        destination_resolution=HONG_KONG_DESTINATION,
        calculated_at=CALCULATED_AT,
    )

    assert result["status"] == "unavailable"
    assert result["warnings"][0].startswith("invalid_current_position")


if __name__ == "__main__":
    test_great_circle_distance()
    test_recent_6h_speed()
    test_recent_24h_fallback()
    test_current_sog_fallback()
    test_no_valid_speed()
    test_stopped_vessel()
    test_eta_datetime_calculation()
    test_eta_v2_uses_navigable_route_distance()
    test_eta_route_failure_fallback()
    test_ais_eta_comparison()
    test_confidence_high()
    test_confidence_medium()
    test_confidence_low()
    test_malformed_input()
    print("test_eta_engine.py passed")

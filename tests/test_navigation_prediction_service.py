from datetime import datetime, timezone

import pytest

from risk_monitor.navigation.prediction_service import (
    NavigationPredictionNotFoundError,
    VesselNavigationPredictionService,
)


NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
VESSEL_ID = "7d74ed40-8ef3-47a8-bf18-a93262f8f771"
MMSI = "477123456"


class _Repository:
    def __init__(self, *, vessel=True, latest=True, route=True, speeds=None):
        self.vessel = {"id": VESSEL_ID, "mmsi": MMSI} if vessel else None
        self.latest = (
            {
                "vessel_id": VESSEL_ID,
                "mmsi": MMSI,
                "latitude": 0,
                "longitude": 5,
                "sog": 12,
                "cog": 90,
                "destination": "SGSIN",
                "observed_at": "2026-09-05T11:55:00Z",
            }
            if latest
            else None
        )
        self.route = (
            {
                "route_prediction_id": "prediction-1",
                "route_version": 2,
                "route_geojson": {
                    "type": "LineString",
                    "coordinates": [[0, 0], [10, 0]],
                },
                "route_method": "land_avoidance_baseline",
                "destination_unlocode": "SGSIN",
                "destination_normalized": "Singapore",
                "route_update_reason": "initial_route",
            }
            if route
            else None
        )
        self.speeds = speeds if speeds is not None else [10, 12, 14]

    def get_vessel(self, vessel_id):
        return self.vessel if vessel_id == VESSEL_ID else None

    def get_latest_position(self, vessel_id):
        return self.latest if vessel_id == VESSEL_ID else None

    def get_active_route(self, mmsi):
        return self.route if mmsi == MMSI else None

    def get_speed_history(self, mmsi, *, hours, now):
        assert mmsi == MMSI
        assert now == NOW
        if hours == 6:
            return [{"sog": speed} for speed in self.speeds]
        return []


def test_prediction_uses_persisted_route_progress_and_robust_speed():
    result = VesselNavigationPredictionService(_Repository()).get_prediction(
        VESSEL_ID,
        prediction_timestamp=NOW,
    )

    assert result["status"] == "estimated"
    assert result["route"]["prediction_id"] == "prediction-1"
    assert result["route"]["progress"] == pytest.approx(0.5, abs=0.001)
    assert result["route"]["remaining_distance_nm"] == pytest.approx(300.2, rel=0.01)
    assert result["eta"]["estimated_speed_knots"] == 12
    assert result["eta"]["remaining_hours"] == pytest.approx(25.0, rel=0.02)
    assert result["eta"]["estimated_arrival_at"].startswith("2026-09-06T13:")
    assert result["route"]["source"] == "land_avoidance_baseline"
    assert result["route"]["destination_matches_latest_ais"] is True


def test_zero_sog_returns_route_metrics_but_eta_is_partial():
    repository = _Repository(speeds=[0, 0.5])
    repository.latest["sog"] = 0

    result = VesselNavigationPredictionService(repository).get_prediction(
        VESSEL_ID,
        prediction_timestamp=NOW,
    )

    assert result["status"] == "partial"
    assert result["route"]["remaining_distance_nm"] > 0
    assert result["eta"]["estimated_arrival_at"] is None
    assert result["eta"]["remaining_hours"] is None
    assert "vessel_stopped_or_very_low_sog" in result["prediction_quality"]["warnings"]


def test_stale_ais_reduces_confidence_and_adds_warning():
    repository = _Repository()
    repository.latest["observed_at"] = "2026-09-03T00:00:00Z"

    result = VesselNavigationPredictionService(repository).get_prediction(
        VESSEL_ID,
        prediction_timestamp=NOW,
    )

    assert result["prediction_quality"]["confidence"] < 0.3
    assert "stale_ais" in result["prediction_quality"]["warnings"]


def test_active_route_destination_mismatch_is_exposed_for_frontend():
    repository = _Repository()
    repository.latest["destination"] = "MYPKG"

    result = VesselNavigationPredictionService(repository).get_prediction(
        VESSEL_ID,
        prediction_timestamp=NOW,
    )

    assert result["route"]["latest_ais_destination"] == "MYPKG"
    assert result["route"]["destination_matches_latest_ais"] is False
    assert (
        "active_route_destination_mismatch"
        in result["prediction_quality"]["warnings"]
    )


def test_observed_ais_alias_matches_canonical_route_destination():
    repository = _Repository()
    repository.latest["destination"] = "NLRTM AND"
    repository.route["destination_unlocode"] = "NLRTM"
    repository.route["destination_normalized"] = "Rotterdam"

    result = VesselNavigationPredictionService(repository).get_prediction(
        VESSEL_ID,
        prediction_timestamp=NOW,
    )

    assert result["route"]["destination_matches_latest_ais"] is True
    assert (
        "active_route_destination_mismatch"
        not in result["prediction_quality"]["warnings"]
    )

@pytest.mark.parametrize(
    ("repository", "message"),
    [
        (_Repository(vessel=False), "Vessel not found."),
        (_Repository(latest=False), "Latest position not found."),
        (_Repository(route=False), "Active route prediction not found."),
    ],
)
def test_missing_required_persisted_data_is_reported(repository, message):
    with pytest.raises(NavigationPredictionNotFoundError, match=message):
        VesselNavigationPredictionService(repository).get_prediction(
            VESSEL_ID,
            prediction_timestamp=NOW,
        )

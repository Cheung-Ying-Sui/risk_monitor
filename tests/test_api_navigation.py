from fastapi.testclient import TestClient

from api.main import app
from api.routes.navigation import get_navigation_prediction_service
from risk_monitor.navigation.prediction_service import (
    NavigationPredictionNotFoundError,
)


VESSEL_ID = "7d74ed40-8ef3-47a8-bf18-a93262f8f771"


class _Service:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def get_prediction(self, vessel_id):
        if self.error:
            raise self.error
        assert vessel_id == VESSEL_ID
        return self.result


def _prediction():
    return {
        "status": "estimated",
        "vessel_id": VESSEL_ID,
        "mmsi": "477123456",
        "prediction_timestamp": "2026-09-05T12:00:00Z",
        "based_on_observed_at": "2026-09-05T11:55:00Z",
        "destination": {
            "port_id": "SGSIN",
            "name": "Singapore",
            "confidence": 0.95,
        },
        "route": {
            "prediction_id": "prediction-1",
            "version": 1,
            "geojson": {"type": "LineString", "coordinates": [[0, 0], [10, 0]]},
            "remaining_geojson": {
                "type": "LineString",
                "coordinates": [[5, 0], [10, 0]],
            },
            "remaining_distance_nm": 300.2,
            "total_distance_nm": 600.4,
            "progress": 0.5,
            "cross_track_error_nm": 0,
            "cross_track_error_m": 0,
            "projected_position": {"longitude": 5, "latitude": 0},
            "source": "persisted_route",
            "status": "on_route",
        },
        "eta": {
            "estimated_arrival_at": "2026-09-06T13:00:00Z",
            "remaining_hours": 25,
            "estimated_speed_knots": 12,
            "speed_method": "recent_6h_moving_sog_median",
            "speed_sample_count": 3,
            "speed_variability": 1,
            "confidence": 0.8,
        },
        "risk_zone_crossings": [],
        "prediction_quality": {
            "confidence": 0.8,
            "ais_age_seconds": 300,
            "reroute_reason": "initial_route",
            "warnings": [],
        },
    }


def teardown_function():
    app.dependency_overrides.clear()


def test_navigation_prediction_endpoint_returns_aggregated_phase_one_response():
    app.dependency_overrides[get_navigation_prediction_service] = lambda: _Service(
        result=_prediction()
    )
    client = TestClient(app)

    response = client.get(f"/api/v1/vessels/{VESSEL_ID}/navigation-prediction")

    assert response.status_code == 200
    body = response.json()
    assert body["route"]["progress"] == 0.5
    assert body["route"]["remaining_distance_nm"] == 300.2
    assert body["eta"]["remaining_hours"] == 25


def test_navigation_prediction_endpoint_returns_404_for_missing_route():
    app.dependency_overrides[get_navigation_prediction_service] = lambda: _Service(
        error=NavigationPredictionNotFoundError(
            "Active route prediction not found."
        )
    )
    client = TestClient(app)

    response = client.get(f"/api/v1/vessels/{VESSEL_ID}/navigation-prediction")

    assert response.status_code == 404
    assert response.json() == {"detail": "Active route prediction not found."}

from fastapi.testclient import TestClient

from api.main import app
from api.routes.risk_zones import get_risk_zone_repository


class FakeRiskZoneRepository:
    def __init__(self, zones=None, error=None):
        self.zones = zones or []
        self.error = error

    def get_active_risk_zones_geojson(self):
        if self.error:
            raise self.error
        return self.zones


def _client(repository):
    app.dependency_overrides[get_risk_zone_repository] = lambda: repository
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_lists_only_active_maritime_risk_zones_as_geojson():
    client = _client(
        FakeRiskZoneRepository(
            zones=[
                {
                    "zone_id": "zone-1",
                    "zone_version_id": "version-1",
                    "zone_name": "Gulf test area",
                    "zone_type": "maritime",
                    "source": "JWLA",
                    "source_document": "JWLA-033",
                    "effective_date": "2026-01-01",
                    "geometry_geojson": {
                        "type": "Polygon",
                        "coordinates": [[[50.0, 20.0], [51.0, 20.0], [51.0, 21.0], [50.0, 20.0]]],
                    },
                },
                {
                    "zone_name": "Country test area",
                    "zone_type": "country",
                    "geometry_geojson": {
                        "type": "Polygon",
                        "coordinates": [[[1.0, 1.0], [2.0, 1.0], [2.0, 2.0], [1.0, 1.0]]],
                    },
                },
            ]
        )
    )

    response = client.get("/api/v1/risk-zones")

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 1
    assert body["features"][0]["properties"]["zone_name"] == "Gulf test area"
    assert body["features"][0]["geometry"]["type"] == "Polygon"


def test_skips_invalid_geometry():
    client = _client(
        FakeRiskZoneRepository(
            zones=[
                {
                    "zone_name": "Invalid maritime area",
                    "zone_type": "maritime",
                    "geometry_geojson": {"type": "Point", "coordinates": [50.0, 20.0]},
                }
            ]
        )
    )

    response = client.get("/api/v1/risk-zones")

    assert response.status_code == 200
    assert response.json()["features"] == []


def test_returns_server_error_when_repository_query_fails():
    client = _client(FakeRiskZoneRepository(error=RuntimeError("rpc failed")))

    response = client.get("/api/v1/risk-zones")

    assert response.status_code == 500
    assert response.json()["detail"] == "Risk zone repository query failed."

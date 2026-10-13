from fastapi.testclient import TestClient

from api.main import app
from api.routes.vessels import (
    get_vessel_read_repository,
    get_vessel_search_service,
)


class _FakeVesselRepository:
    def __init__(
        self,
        tracked_vessels=None,
        vessels_by_mmsi=None,
        latest_positions=None,
        tracks_by_mmsi=None,
        error=None,
    ):
        self.tracked_vessels = tracked_vessels or []
        self.vessels_by_mmsi = vessels_by_mmsi or {}
        self.latest_positions = latest_positions or []
        self.tracks_by_mmsi = tracks_by_mmsi or {}
        self.error = error

    def get_tracked_vessels(self):
        if self.error:
            raise self.error

        return self.tracked_vessels

    def get_vessel_by_mmsi(self, mmsi):
        if self.error:
            raise self.error

        return self.vessels_by_mmsi.get(str(mmsi))

    def get_vessel_by_imo(self, imo):
        if self.error:
            raise self.error

        for vessel in self.vessels_by_mmsi.values():
            if str(vessel.get("imo")) == str(imo):
                return vessel

        return None

    def get_vessel_by_id(self, vessel_id):
        if self.error:
            raise self.error

        for vessel in self.vessels_by_mmsi.values():
            if str(vessel.get("id")) == str(vessel_id):
                return vessel

        return None

    def get_track_by_mmsi(self, mmsi, limit):
        if self.error:
            raise self.error

        return self.tracks_by_mmsi.get(str(mmsi), [])[:limit]

    def get_recorded_vessels(self, limit):
        if self.error:
            raise self.error

        return []

    def get_latest_position_by_mmsi(self, mmsi):
        if self.error:
            raise self.error

        for latest_position in self.latest_positions:
            if str(latest_position.get("mmsi")) == str(mmsi):
                return latest_position

        return None

    def get_latest_position_by_vessel_id(self, vessel_id):
        if self.error:
            raise self.error

        for latest_position in self.latest_positions:
            if str(latest_position.get("vessel_id")) == str(vessel_id):
                return latest_position

        return None


class _FakeVesselSearchService:
    def __init__(self, search_result=None, onboard_result=None, error=None):
        self.search_result = search_result
        self.onboard_result = onboard_result
        self.error = error

    def search(self, mmsi=None, imo=None):
        if self.error:
            raise self.error

        return self.search_result

    def onboard(self, candidate_data):
        if self.error:
            raise self.error

        return self.onboard_result


def _client(repository, search_service=None):
    app.dependency_overrides[get_vessel_read_repository] = lambda: repository
    if search_service:
        app.dependency_overrides[get_vessel_search_service] = (
            lambda: search_service
        )
    return TestClient(app, raise_server_exceptions=False)


def teardown_function():
    app.dependency_overrides.clear()


def test_health_check_still_returns_ok():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_vessels_returns_stable_api_schema_with_core_vessel_id():
    client = _client(
        _FakeVesselRepository(
            tracked_vessels=[
                {
                    "id": "tracking-record-id",
                    "vessel_id": "7d74ed40-8ef3-47a8-bf18-a93262f8f771",
                    "mmsi": "477123456",
                }
            ],
            vessels_by_mmsi={
                "477123456": {
                    "id": "7d74ed40-8ef3-47a8-bf18-a93262f8f771",
                    "mmsi": "477123456",
                    "imo": "9876543",
                    "ship_name": "PACIFIC TRADER",
                    "ship_type": "Cargo",
                    "callsign": "VRAB1",
                    "flag_state": "HK",
                }
            },
        )
    )

    response = client.get("/api/v1/vessels")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "7d74ed40-8ef3-47a8-bf18-a93262f8f771",
            "mmsi": "477123456",
            "imo": "9876543",
            "name": "PACIFIC TRADER",
            "ship_type": "Cargo",
            "flag_state": "HK",
            "callsign": "VRAB1",
        }
    ]


def test_latest_position_returns_stable_api_schema():
    vessel_id = "7d74ed40-8ef3-47a8-bf18-a93262f8f771"
    client = _client(
        _FakeVesselRepository(
            tracked_vessels=[
                {
                    "id": "tracking-record-id",
                    "vessel_id": vessel_id,
                    "mmsi": "477123456",
                }
            ],
            latest_positions=[
                {
                    "vessel_id": vessel_id,
                    "position_id": 123,
                    "mmsi": "477123456",
                    "latitude": "22.3193",
                    "longitude": "114.1694",
                    "sog": "12.5",
                    "cog": "88.2",
                    "heading": "90",
                    "nav_status": "Under way",
                    "destination": "HONG KONG",
                    "observed_at": "2026-08-15T12:30:00Z",
                    "source_id": "source-id",
                }
            ],
        )
    )

    response = client.get(f"/api/v1/vessels/{vessel_id}/latest-position")

    assert response.status_code == 200
    assert response.json() == {
        "vessel_id": vessel_id,
        "latitude": 22.3193,
        "longitude": 114.1694,
        "sog": 12.5,
        "cog": 88.2,
        "heading": 90.0,
        "navigation_status": "Under way",
        "destination": "HONG KONG",
        "observed_at": "2026-08-15T12:30:00Z",
    }


def test_latest_position_returns_404_when_vessel_does_not_exist():
    client = _client(
        _FakeVesselRepository(
            tracked_vessels=[
                {
                    "vessel_id": "7d74ed40-8ef3-47a8-bf18-a93262f8f771",
                    "mmsi": "477123456",
                }
            ],
        )
    )

    response = client.get(
        "/api/v1/vessels/7fc443fc-7659-43a8-860a-38f71453417a/latest-position"
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Vessel not found."}


def test_latest_position_returns_404_when_position_is_missing():
    vessel_id = "7d74ed40-8ef3-47a8-bf18-a93262f8f771"
    client = _client(
        _FakeVesselRepository(
            tracked_vessels=[
                {
                    "vessel_id": vessel_id,
                    "mmsi": "477123456",
                }
            ],
            latest_positions=[],
        )
    )

    response = client.get(f"/api/v1/vessels/{vessel_id}/latest-position")

    assert response.status_code == 404
    assert response.json() == {"detail": "Latest position not found."}


def test_repository_error_returns_500():
    client = _client(_FakeVesselRepository(error=RuntimeError("database down")))

    response = client.get("/api/v1/vessels")

    assert response.status_code == 500
    assert response.json() == {"detail": "Vessel repository query failed."}


def test_historical_track_is_available_when_vessel_is_not_actively_tracked():
    vessel_id = "7d74ed40-8ef3-47a8-bf18-a93262f8f771"
    client = _client(
        _FakeVesselRepository(
            tracked_vessels=[],
            vessels_by_mmsi={
                "477123456": {
                    "id": vessel_id,
                    "mmsi": "477123456",
                    "ship_name": "PACIFIC TRADER",
                }
            },
            tracks_by_mmsi={
                "477123456": [
                    {
                        "id": 123,
                        "mmsi": "477123456",
                        "latitude": "22.3193",
                        "longitude": "114.1694",
                        "sog": "12.5",
                        "cog": "88.2",
                        "heading": "90",
                        "nav_status": "Under way",
                        "destination": "HONG KONG",
                        "observed_at": "2026-08-15T12:30:00Z",
                        "received_at": "2026-08-15T12:31:00Z",
                    }
                ]
            },
        )
    )

    response = client.get(f"/api/v1/vessels/{vessel_id}/track")

    assert response.status_code == 200
    assert response.json()[0]["vessel_id"] == vessel_id
    assert response.json()[0]["latitude"] == 22.3193


def test_search_vessel_by_mmsi_returns_master_data_tracking_and_position():
    vessel_id = "7d74ed40-8ef3-47a8-bf18-a93262f8f771"
    client = _client(
        _FakeVesselRepository(),
        _FakeVesselSearchService(
            search_result={
                "source": "local",
                "is_persisted": True,
                "id": vessel_id,
                "mmsi": "477123456",
                "imo": "9876543",
                "name": "PACIFIC TRADER",
                "ship_type": "Cargo",
                "flag_state": "HK",
                "callsign": "VRAB1",
                "is_tracked": True,
                "latest_position": {
                    "vessel_id": vessel_id,
                    "latitude": 22.3193,
                    "longitude": 114.1694,
                    "sog": 12.5,
                    "cog": 88.2,
                    "heading": 90,
                    "navigation_status": "Under way",
                    "destination": "HONG KONG",
                    "observed_at": "2026-08-15T12:30:00Z",
                },
            }
        ),
    )

    response = client.get("/api/v1/vessels/search?mmsi=477123456")

    assert response.status_code == 200
    assert response.json() == {
        "source": "local",
        "is_persisted": True,
        "id": vessel_id,
        "mmsi": "477123456",
        "imo": "9876543",
        "name": "PACIFIC TRADER",
        "ship_type": "Cargo",
        "flag_state": "HK",
        "callsign": "VRAB1",
        "is_tracked": True,
        "latest_position": {
            "vessel_id": vessel_id,
            "latitude": 22.3193,
            "longitude": 114.1694,
            "sog": 12.5,
            "cog": 88.2,
            "heading": 90.0,
            "navigation_status": "Under way",
            "destination": "HONG KONG",
            "observed_at": "2026-08-15T12:30:00Z",
        },
    }


def test_search_vessel_external_candidate_has_null_id():
    client = _client(
        _FakeVesselRepository(),
        _FakeVesselSearchService(
            search_result={
                "source": "external",
                "is_persisted": False,
                "id": None,
                "mmsi": "477123456",
                "imo": None,
                "name": "PACIFIC TRADER",
                "ship_type": "Cargo",
                "flag_state": "HK",
                "callsign": "VRAB1",
                "is_tracked": False,
                "latest_position": {
                    "latitude": 22.3193,
                    "longitude": 114.1694,
                    "observed_at": "2026-08-15T12:30:00Z",
                },
            }
        ),
    )

    response = client.get("/api/v1/vessels/search?mmsi=477123456")

    assert response.status_code == 200
    assert response.json()["id"] is None
    assert response.json()["source"] == "external"
    assert response.json()["is_persisted"] is False


def test_onboard_vessel_returns_persisted_vessel_with_warnings():
    vessel_id = "7d74ed40-8ef3-47a8-bf18-a93262f8f771"
    client = _client(
        _FakeVesselRepository(),
        _FakeVesselSearchService(
            onboard_result={
                "source": "local",
                "is_persisted": True,
                "id": vessel_id,
                "mmsi": "477123456",
                "imo": "9876543",
                "name": "PACIFIC TRADER",
                "ship_type": "Cargo",
                "flag_state": None,
                "callsign": None,
                "is_tracked": True,
                "latest_position": None,
                "warnings": ["Latest position persistence failed."],
            }
        ),
    )

    response = client.post(
        "/api/v1/vessels/onboard",
        json={
            "source": "chinaports",
            "mmsi": "477123456",
            "imo": "9876543",
            "name": "PACIFIC TRADER",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "source": "local",
        "is_persisted": True,
        "id": vessel_id,
        "mmsi": "477123456",
        "imo": "9876543",
        "name": "PACIFIC TRADER",
        "ship_type": "Cargo",
        "flag_state": None,
        "callsign": None,
        "is_tracked": True,
        "latest_position": None,
        "warnings": ["Latest position persistence failed."],
    }


def test_search_vessel_by_imo_returns_untracked_vessel():
    vessel_id = "7d74ed40-8ef3-47a8-bf18-a93262f8f771"
    client = _client(
        _FakeVesselRepository(),
        _FakeVesselSearchService(
            search_result={
                "source": "local",
                "is_persisted": True,
                "id": vessel_id,
                "mmsi": "477123456",
                "imo": "9876543",
                "name": "PACIFIC TRADER",
                "ship_type": None,
                "flag_state": None,
                "callsign": None,
                "is_tracked": False,
                "latest_position": None,
            }
        )
    )

    response = client.get("/api/v1/vessels/search?imo=9876543")

    assert response.status_code == 200
    assert response.json()["id"] == vessel_id
    assert response.json()["is_tracked"] is False


def test_search_vessel_returns_404_when_vessel_does_not_exist():
    from risk_monitor.vessel_search_service import VesselNotFoundError

    client = _client(
        _FakeVesselRepository(),
        _FakeVesselSearchService(error=VesselNotFoundError("Vessel not found.")),
    )

    response = client.get("/api/v1/vessels/search?mmsi=477123456")

    assert response.status_code == 404
    assert response.json() == {"detail": "Vessel not found."}


def test_search_vessel_returns_null_when_latest_position_is_missing():
    vessel_id = "7d74ed40-8ef3-47a8-bf18-a93262f8f771"
    client = _client(
        _FakeVesselRepository(),
        _FakeVesselSearchService(
            search_result={
                "source": "local",
                "is_persisted": True,
                "id": vessel_id,
                "mmsi": "477123456",
                "imo": "9876543",
                "name": "PACIFIC TRADER",
                "ship_type": None,
                "flag_state": None,
                "callsign": None,
                "is_tracked": False,
                "latest_position": None,
            }
        )
    )

    response = client.get("/api/v1/vessels/search?mmsi=477123456")

    assert response.status_code == 200
    assert response.json()["latest_position"] is None


def test_search_vessel_requires_imo_or_mmsi():
    from risk_monitor.vessel_search_service import VesselValidationError

    client = _client(
        _FakeVesselRepository(),
        _FakeVesselSearchService(
            error=VesselValidationError("Either imo or mmsi is required.")
        ),
    )

    response = client.get("/api/v1/vessels/search")

    assert response.status_code == 422
    assert response.json() == {"detail": "Either imo or mmsi is required."}


def test_search_imo_only_local_miss_returns_422_explanation():
    from risk_monitor.vessel_search_service import ExternalSearchUnsupportedError

    client = _client(
        _FakeVesselRepository(),
        _FakeVesselSearchService(
            error=ExternalSearchUnsupportedError(
                "External fallback currently requires MMSI."
            )
        ),
    )

    response = client.get("/api/v1/vessels/search?imo=9632313")

    assert response.status_code == 422
    assert response.json() == {
        "detail": "External fallback currently requires MMSI."
    }


def test_external_source_unavailable_returns_503():
    from risk_monitor.vessel_search_service import ExternalSourceUnavailableError

    client = _client(
        _FakeVesselRepository(),
        _FakeVesselSearchService(
            error=ExternalSourceUnavailableError(
                "External vessel source unavailable."
            )
        ),
    )

    response = client.get("/api/v1/vessels/search?mmsi=477222100")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "External vessel source unavailable."
    }


def test_onboard_conflict_returns_409():
    from risk_monitor.vessel_search_service import VesselConflictError

    client = _client(
        _FakeVesselRepository(),
        _FakeVesselSearchService(
            error=VesselConflictError(
                "IMO is already associated with a different MMSI."
            )
        ),
    )

    response = client.post(
        "/api/v1/vessels/onboard",
        json={
            "source": "chinaports",
            "mmsi": "477222100",
            "imo": "9632313",
            "name": "XIN HAI TONG 56",
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "IMO is already associated with a different MMSI."
    }

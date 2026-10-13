from fastapi.testclient import TestClient

from api.main import app
from api.routes.tracking import get_tracking_management_repository


class _FakeTrackingRepository:
    def __init__(self, vessels=None, tracking=None, error=None):
        self.vessels = vessels or {}
        self.tracking = tracking or {}
        self.error = error

    def get_vessel_by_id(self, vessel_id):
        if self.error:
            raise self.error

        return self.vessels.get(str(vessel_id))

    def activate_tracking_by_vessel(self, vessel):
        if self.error:
            raise self.error

        vessel_id = str(vessel["id"])
        existing = self.tracking.get(vessel_id)
        if existing:
            existing["is_active"] = True
            return existing

        status = {
            "vessel_id": vessel_id,
            "mmsi": vessel["mmsi"],
            "is_active": True,
            "tracking_mode": "history_tracking",
            "priority": 0,
        }
        self.tracking[vessel_id] = status
        return status

    def deactivate_tracking_by_vessel_id(self, vessel_id):
        if self.error:
            raise self.error

        existing = self.tracking.get(str(vessel_id))
        if not existing:
            return None

        existing["is_active"] = False
        return existing


def _client(repository):
    app.dependency_overrides[get_tracking_management_repository] = (
        lambda: repository
    )
    return TestClient(app, raise_server_exceptions=False)


def teardown_function():
    app.dependency_overrides.clear()


def test_add_tracking_creates_new_active_membership():
    vessel_id = "7d74ed40-8ef3-47a8-bf18-a93262f8f771"
    repository = _FakeTrackingRepository(
        vessels={
            vessel_id: {
                "id": vessel_id,
                "mmsi": "477123456",
            }
        }
    )
    client = _client(repository)

    response = client.post(f"/api/v1/tracking/vessels/{vessel_id}")

    assert response.status_code == 200
    assert response.json() == {
        "vessel_id": vessel_id,
        "is_active": True,
    }
    assert repository.tracking[vessel_id]["tracking_mode"] == "history_tracking"


def test_add_tracking_reactivates_inactive_membership_idempotently():
    vessel_id = "7d74ed40-8ef3-47a8-bf18-a93262f8f771"
    repository = _FakeTrackingRepository(
        vessels={
            vessel_id: {
                "id": vessel_id,
                "mmsi": "477123456",
            }
        },
        tracking={
            vessel_id: {
                "vessel_id": vessel_id,
                "mmsi": "477123456",
                "is_active": False,
                "tracking_mode": "high_risk_monitoring",
                "priority": 9,
                "metadata": {"keep": True},
            }
        },
    )
    client = _client(repository)

    response = client.post(f"/api/v1/tracking/vessels/{vessel_id}")

    assert response.status_code == 200
    assert response.json() == {
        "vessel_id": vessel_id,
        "is_active": True,
    }
    assert repository.tracking[vessel_id]["tracking_mode"] == "high_risk_monitoring"
    assert repository.tracking[vessel_id]["priority"] == 9
    assert repository.tracking[vessel_id]["metadata"] == {"keep": True}


def test_add_tracking_already_active_is_idempotent():
    vessel_id = "7d74ed40-8ef3-47a8-bf18-a93262f8f771"
    repository = _FakeTrackingRepository(
        vessels={
            vessel_id: {
                "id": vessel_id,
                "mmsi": "477123456",
            }
        },
        tracking={
            vessel_id: {
                "vessel_id": vessel_id,
                "mmsi": "477123456",
                "is_active": True,
            }
        },
    )
    client = _client(repository)

    response = client.post(f"/api/v1/tracking/vessels/{vessel_id}")

    assert response.status_code == 200
    assert response.json() == {
        "vessel_id": vessel_id,
        "is_active": True,
    }


def test_add_tracking_invalid_vessel_returns_404():
    client = _client(_FakeTrackingRepository())

    response = client.post(
        "/api/v1/tracking/vessels/7d74ed40-8ef3-47a8-bf18-a93262f8f771"
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Vessel not found."}


def test_stop_tracking_deactivates_active_membership():
    vessel_id = "7d74ed40-8ef3-47a8-bf18-a93262f8f771"
    repository = _FakeTrackingRepository(
        vessels={
            vessel_id: {
                "id": vessel_id,
                "mmsi": "477123456",
            }
        },
        tracking={
            vessel_id: {
                "vessel_id": vessel_id,
                "mmsi": "477123456",
                "is_active": True,
            }
        },
    )
    client = _client(repository)

    response = client.patch(
        f"/api/v1/tracking/vessels/{vessel_id}",
        json={"is_active": False},
    )

    assert response.status_code == 200
    assert response.json() == {
        "vessel_id": vessel_id,
        "is_active": False,
    }
    assert repository.tracking[vessel_id]["is_active"] is False


def test_stop_tracking_already_inactive_is_idempotent():
    vessel_id = "7d74ed40-8ef3-47a8-bf18-a93262f8f771"
    repository = _FakeTrackingRepository(
        vessels={
            vessel_id: {
                "id": vessel_id,
                "mmsi": "477123456",
            }
        },
        tracking={
            vessel_id: {
                "vessel_id": vessel_id,
                "mmsi": "477123456",
                "is_active": False,
            }
        },
    )
    client = _client(repository)

    response = client.patch(
        f"/api/v1/tracking/vessels/{vessel_id}",
        json={"is_active": False},
    )

    assert response.status_code == 200
    assert response.json() == {
        "vessel_id": vessel_id,
        "is_active": False,
    }


def test_stop_tracking_untracked_existing_vessel_is_idempotent():
    vessel_id = "7d74ed40-8ef3-47a8-bf18-a93262f8f771"
    repository = _FakeTrackingRepository(
        vessels={
            vessel_id: {
                "id": vessel_id,
                "mmsi": "477123456",
            }
        }
    )
    client = _client(repository)

    response = client.patch(
        f"/api/v1/tracking/vessels/{vessel_id}",
        json={"is_active": False},
    )

    assert response.status_code == 200
    assert response.json() == {
        "vessel_id": vessel_id,
        "is_active": False,
    }


def test_stop_tracking_invalid_vessel_returns_404():
    client = _client(_FakeTrackingRepository())

    response = client.patch(
        "/api/v1/tracking/vessels/7d74ed40-8ef3-47a8-bf18-a93262f8f771",
        json={"is_active": False},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Vessel not found."}


def test_tracking_repository_error_returns_500():
    vessel_id = "7d74ed40-8ef3-47a8-bf18-a93262f8f771"
    client = _client(_FakeTrackingRepository(error=RuntimeError("database down")))

    response = client.post(f"/api/v1/tracking/vessels/{vessel_id}")

    assert response.status_code == 500
    assert response.json() == {"detail": "Tracking repository query failed."}

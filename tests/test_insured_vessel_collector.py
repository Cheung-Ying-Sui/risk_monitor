import pytest

from scripts import fetch_vessel_positions_job as job


class FakeInsuranceService:
    def __init__(self):
        self.synced = []

    def sync_imo(self, imo):
        self.synced.append(imo)
        return "tracking"


def test_collector_refreshes_insured_vessel_by_imo(monkeypatch):
    service = FakeInsuranceService()
    monkeypatch.setattr(job, "get_vessel_by_mmsi", lambda mmsi: {"imo": "9127136", "mmsi": mmsi})
    monkeypatch.setattr(job, "get_latest_position_by_mmsi", lambda mmsi: {"observed_at": "2026-10-10T01:00:00Z"})
    monkeypatch.setattr(job, "fetch_ship_info", lambda mmsi: (_ for _ in ()).throw(AssertionError("Chinaports should not be called")))

    result = job.process_vessel({"mmsi": "636123456", "tracking_mode": "history_tracking"}, {"9127136"}, service)

    assert service.synced == ["9127136"]
    assert result["status"] == "insurance_ais_refreshed"


def test_collector_keeps_existing_source_for_demo_vessel(monkeypatch):
    service = FakeInsuranceService()
    monkeypatch.setattr(job, "get_vessel_by_mmsi", lambda mmsi: {"imo": "9999999", "mmsi": mmsi})
    calls = []
    def fetch(**kwargs):
        calls.append(kwargs)
        return {"mmsi": kwargs["mmsi"], "imo": kwargs["imo"]}
    monkeypatch.setattr(job, "fetch_ship_info", fetch)
    monkeypatch.setattr(job, "upsert_vessel", lambda data: [{"id": "vessel-1"}])
    monkeypatch.setattr(job, "upsert_position", lambda data: [{"id": 1}])

    result = job.process_vessel({"mmsi": "636123456", "tracking_mode": "history_tracking"}, {"9127136"}, service)

    assert service.synced == []
    assert result["mmsi"] == "636123456"
    assert calls == [{"imo": "9999999", "mmsi": "636123456"}]


def test_collector_without_imo_uses_mmsi(monkeypatch):
    calls = []
    monkeypatch.setattr(job, "get_vessel_by_mmsi", lambda mmsi: {"mmsi": mmsi})
    def fetch(**kwargs):
        calls.append(kwargs)
        return {"mmsi": kwargs["mmsi"]}
    monkeypatch.setattr(job, "fetch_ship_info", fetch)
    monkeypatch.setattr(job, "upsert_vessel", lambda data: [{"id": "vessel-1"}])
    monkeypatch.setattr(job, "upsert_position", lambda data: [{"id": 1}])
    job.process_vessel({"mmsi": "636123456"})
    assert calls == [{"imo": None, "mmsi": "636123456"}]


def test_collector_never_saves_mismatched_identity(monkeypatch):
    monkeypatch.setattr(job, "get_vessel_by_mmsi", lambda mmsi: {"imo": "9127136", "mmsi": mmsi})
    monkeypatch.setattr(job, "fetch_ship_info", lambda **kw: {"imo": "9999999", "mmsi": kw["mmsi"]})
    monkeypatch.setattr(job, "upsert_vessel", lambda data: pytest.fail("Wrong vessel must not be saved"))
    monkeypatch.setattr(job, "upsert_position", lambda data: pytest.fail("Wrong position must not be saved"))
    with pytest.raises(RuntimeError, match="identity mismatch"):
        job.process_vessel({"mmsi": "636123456"})

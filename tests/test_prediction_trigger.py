from unittest.mock import patch

from risk_monitor.navigation import prediction_trigger
import pytest


@pytest.fixture(autouse=True)
def no_insurance_database(monkeypatch):
    monkeypatch.setattr(prediction_trigger, 'refresh_insurance_voyages', lambda *_: None)


def test_successful_refresh_returns_prediction_identity():
    with patch.object(
        prediction_trigger,
        "get_rolling_route_prediction",
        return_value={
            "status": "estimated",
            "route_updated": True,
            "route_update_reason": "destination_changed",
            "active_route": {"route_prediction_id": "route-2"},
            "warnings": [],
        },
    ):
        result = prediction_trigger.refresh_prediction_after_position(
            vessel_id="vessel-1",
            mmsi="477123456",
            observed_at="2026-09-05T12:00:00Z",
        )

    assert result["status"] == "updated"
    assert result["prediction_id"] == "route-2"
    assert result["route_updated"] is True
    assert result["route_update_reason"] == "destination_changed"


def test_prediction_failure_is_returned_and_not_raised():
    with patch.object(
        prediction_trigger,
        "get_rolling_route_prediction",
        side_effect=RuntimeError("route service unavailable"),
    ):
        result = prediction_trigger.refresh_prediction_after_position(
            vessel_id="vessel-1",
            mmsi="477123456",
        )

    assert result["status"] == "failed"
    assert result["error_type"] == "RuntimeError"


def test_missing_identity_skips_prediction_refresh():
    result = prediction_trigger.refresh_prediction_after_position(
        vessel_id="",
        mmsi="477123456",
    )

    assert result == {
        "status": "skipped",
        "vessel_id": None,
        "mmsi": "477123456",
        "reason": "missing_vessel_identity",
    }


def test_insurance_conflict_does_not_fall_back_to_generic_route(monkeypatch):
    monkeypatch.setattr(prediction_trigger, 'refresh_insurance_voyages', lambda *_: {'status': 'destination_mismatch', 'warnings': ['needs_review']})
    with patch.object(prediction_trigger, 'get_rolling_route_prediction') as generic:
        result = prediction_trigger.refresh_prediction_after_position(vessel_id='new-vessel', mmsi='123456789')
    assert result['status'] == 'destination_mismatch'
    generic.assert_not_called()


def test_finished_voyage_does_not_generate_generic_route(monkeypatch):
    monkeypatch.setattr(prediction_trigger, 'refresh_insurance_voyages', lambda *_: {'status': 'voyage_completed'})
    with patch.object(prediction_trigger, 'get_rolling_route_prediction') as generic:
        result = prediction_trigger.refresh_prediction_after_position(vessel_id='new-vessel', mmsi='123456789')
    assert result['status'] == 'voyage_completed'
    generic.assert_not_called()

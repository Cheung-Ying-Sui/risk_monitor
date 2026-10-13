import pytest

from risk_monitor.insurance_screening import prepare_shipments_for_screening


def test_submission_queues_original_names_without_searching():
    rows = [{"vessel_name": "TEST VESSEL", "extra_data": {
        "shipper": "Original Shipper", "sanctions_screening": {"status": "completed"},
        "sanctions_workflow": {"report": {"document_id": "forged"}},
    }}]
    prepared = prepare_shipments_for_screening(rows, "Insured Company")
    extra = prepared[0]["extra_data"]
    assert extra["insured_name"] == "Insured Company"
    assert extra["shipper"] == "Original Shipper"
    assert extra["sanctions_screening"]["status"] == "pending"
    assert "sanctions_workflow" not in extra
    assert rows[0]["extra_data"]["sanctions_screening"]["status"] == "completed"


def test_submission_requires_at_least_one_party():
    with pytest.raises(ValueError, match="待筛查主体"):
        prepare_shipments_for_screening([{"extra_data": {}}], None)

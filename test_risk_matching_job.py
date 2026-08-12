from unittest.mock import patch

from scripts import run_risk_matching_job


def test_no_active_vessel():
    with patch.object(
        run_risk_matching_job,
        "get_tracked_vessels",
        return_value=[],
    ), patch.object(
        run_risk_matching_job,
        "get_tracked_vessels_in_risk_zones",
        return_value=[],
    ), patch.object(
        run_risk_matching_job,
        "record_current_risk_matches",
        return_value={"inserted_count": 0},
    ):
        result = run_risk_matching_job.run_job()

    assert result["tracked_vessel_count"] == 0
    assert result["matched_vessel_count"] == 0
    assert result["inserted_match_count"] == 0
    assert result["errors"] == []


def test_active_vessel_without_risk_hit():
    with patch.object(
        run_risk_matching_job,
        "get_tracked_vessels",
        return_value=[{"mmsi": "413123456"}],
    ), patch.object(
        run_risk_matching_job,
        "get_tracked_vessels_in_risk_zones",
        return_value=[],
    ), patch.object(
        run_risk_matching_job,
        "record_current_risk_matches",
        return_value={"inserted_count": 0},
    ):
        result = run_risk_matching_job.run_job()

    assert result["tracked_vessel_count"] == 1
    assert result["matched_vessel_count"] == 0
    assert result["inserted_match_count"] == 0


def test_active_vessel_with_risk_hit():
    with patch.object(
        run_risk_matching_job,
        "get_tracked_vessels",
        return_value=[{"mmsi": "413123456"}],
    ), patch.object(
        run_risk_matching_job,
        "get_tracked_vessels_in_risk_zones",
        return_value=[{"mmsi": "413123456", "zone_id": "zone-1"}],
    ), patch.object(
        run_risk_matching_job,
        "record_current_risk_matches",
        return_value={"inserted_count": 1},
    ):
        result = run_risk_matching_job.run_job()

    assert result["tracked_vessel_count"] == 1
    assert result["matched_vessel_count"] == 1
    assert result["inserted_match_count"] == 1


def test_duplicate_run_inserted_count_zero():
    with patch.object(
        run_risk_matching_job,
        "get_tracked_vessels",
        return_value=[{"mmsi": "413123456"}],
    ), patch.object(
        run_risk_matching_job,
        "get_tracked_vessels_in_risk_zones",
        return_value=[{"mmsi": "413123456", "zone_id": "zone-1"}],
    ), patch.object(
        run_risk_matching_job,
        "record_current_risk_matches",
        return_value={"inserted_count": 0},
    ):
        result = run_risk_matching_job.run_job()

    assert result["matched_vessel_count"] == 1
    assert result["inserted_match_count"] == 0


def test_rpc_error_returns_nonzero_exit_code():
    with patch.object(
        run_risk_matching_job,
        "get_tracked_vessels",
        side_effect=RuntimeError("rpc failed"),
    ):
        exit_code = run_risk_matching_job.main()

    assert exit_code == 1


def test_invalid_response_handling():
    with patch.object(
        run_risk_matching_job,
        "get_tracked_vessels",
        return_value=[],
    ), patch.object(
        run_risk_matching_job,
        "get_tracked_vessels_in_risk_zones",
        return_value=[],
    ), patch.object(
        run_risk_matching_job,
        "record_current_risk_matches",
        return_value={},
    ):
        exit_code = run_risk_matching_job.main()

    assert exit_code == 1


if __name__ == "__main__":
    test_no_active_vessel()
    test_active_vessel_without_risk_hit()
    test_active_vessel_with_risk_hit()
    test_duplicate_run_inserted_count_zero()
    test_rpc_error_returns_nonzero_exit_code()
    test_invalid_response_handling()
    print("test_risk_matching_job.py passed")

from unittest.mock import patch

from scripts import run_route_prediction_job


RECORDS = [
    {"vessel_id": "vessel-1", "mmsi": "477123456"},
    {"vessel_id": "vessel-2", "mmsi": "477654321"},
]


def test_dry_run_lists_vessels_without_refreshing_predictions():
    with patch.object(
        run_route_prediction_job,
        "get_tracked_vessels",
        return_value=RECORDS,
    ), patch.object(
        run_route_prediction_job,
        "refresh_prediction_after_position",
    ) as refresh:
        result = run_route_prediction_job.run_job(dry_run=True)

    assert result["tracked_vessel_count"] == 2
    assert [item["status"] for item in result["results"]] == [
        "planned",
        "planned",
    ]
    refresh.assert_not_called()


def test_job_isolates_per_vessel_prediction_failure():
    with patch.object(
        run_route_prediction_job,
        "get_tracked_vessels",
        return_value=RECORDS,
    ), patch.object(
        run_route_prediction_job,
        "refresh_prediction_after_position",
        side_effect=[
            {"status": "updated", "prediction_id": "route-1"},
            {"status": "failed", "error_type": "RuntimeError"},
        ],
    ):
        result = run_route_prediction_job.run_job()

    assert result["updated_count"] == 1
    assert result["failed_count"] == 1
    assert len(result["results"]) == 2


def test_main_returns_nonzero_when_any_refresh_fails():
    with patch.object(
        run_route_prediction_job,
        "run_job",
        return_value={
            "dry_run": False,
            "tracked_vessel_count": 1,
            "updated_count": 0,
            "failed_count": 1,
            "skipped_count": 0,
        },
    ):
        assert run_route_prediction_job.main([]) == 1

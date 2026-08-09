from datetime import datetime, timezone

from supabase_client import supabase


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def create_collection_run(
    trigger_source="github_actions",
    total_vessels=None,
):
    payload = {
        "started_at": _utc_now(),
        "status": "running",
        "trigger_source": trigger_source,
        "total_vessels": total_vessels,
        "success_count": 0,
        "failed_count": 0,
    }

    result = (
        supabase
        .schema("ingest")
        .table("collection_runs")
        .insert(payload)
        .execute()
    )

    if not result.data:
        raise RuntimeError("Failed to create collection run.")

    return result.data[0]["id"]


def record_collection_item_success(run_id, mmsi):
    if not run_id:
        raise ValueError("run_id is required.")
    if not mmsi:
        raise ValueError("mmsi is required.")

    timestamp = _utc_now()
    payload = {
        "run_id": run_id,
        "mmsi": str(mmsi),
        "status": "success",
        "started_at": timestamp,
        "finished_at": timestamp,
    }

    result = (
        supabase
        .schema("ingest")
        .table("collection_run_items")
        .insert(payload)
        .execute()
    )

    return result.data


def record_collection_item_failure(run_id, mmsi, error_message):
    if not run_id:
        raise ValueError("run_id is required.")
    if not mmsi:
        raise ValueError("mmsi is required.")

    timestamp = _utc_now()
    payload = {
        "run_id": run_id,
        "mmsi": str(mmsi),
        "status": "failed",
        "error_message": str(error_message) if error_message else None,
        "started_at": timestamp,
        "finished_at": timestamp,
    }

    result = (
        supabase
        .schema("ingest")
        .table("collection_run_items")
        .insert(payload)
        .execute()
    )

    return result.data


def finish_collection_run(
    run_id,
    status,
    success_count,
    failed_count,
):
    if not run_id:
        raise ValueError("run_id is required.")

    payload = {
        "finished_at": _utc_now(),
        "status": status,
        "success_count": success_count,
        "failed_count": failed_count,
    }

    result = (
        supabase
        .schema("ingest")
        .table("collection_runs")
        .update(payload)
        .eq("id", run_id)
        .execute()
    )

    return result.data

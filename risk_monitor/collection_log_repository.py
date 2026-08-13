from risk_monitor.supabase_client import supabase


COLLECTION_RUN_FIELDS = (
    "id,started_at,finished_at,status,trigger_source,total_vessels,"
    "success_count,failed_count,created_at"
)

COLLECTION_RUN_ITEM_FIELDS = (
    "id,run_id,mmsi,status,error_message,started_at,finished_at,created_at"
)


def _normalize_limit(limit):
    try:
        normalized_limit = int(limit)
    except (TypeError, ValueError):
        raise ValueError("limit must be an integer.")

    if normalized_limit <= 0:
        raise ValueError("limit must be greater than 0.")

    return normalized_limit


def get_recent_collection_runs(limit=20):
    result = (
        supabase
        .schema("ingest")
        .table("collection_runs")
        .select(COLLECTION_RUN_FIELDS)
        .order(
            "created_at",
            desc=True,
        )
        .limit(_normalize_limit(limit))
        .execute()
    )

    return result.data or []


def get_collection_run_items(run_id):
    if not run_id:
        raise ValueError("run_id is required.")

    result = (
        supabase
        .schema("ingest")
        .table("collection_run_items")
        .select(COLLECTION_RUN_ITEM_FIELDS)
        .eq(
            "run_id",
            str(run_id),
        )
        .order(
            "created_at",
            desc=False,
        )
        .execute()
    )

    return result.data or []


def get_recent_collection_failures(limit=50):
    result = (
        supabase
        .schema("ingest")
        .table("collection_run_items")
        .select(COLLECTION_RUN_ITEM_FIELDS)
        .eq(
            "status",
            "failed",
        )
        .order(
            "created_at",
            desc=True,
        )
        .limit(_normalize_limit(limit))
        .execute()
    )

    return result.data or []


def get_latest_collection_run():
    result = (
        supabase
        .schema("ingest")
        .table("collection_runs")
        .select(COLLECTION_RUN_FIELDS)
        .order(
            "created_at",
            desc=True,
        )
        .limit(1)
        .execute()
    )

    if not result.data:
        return None

    return result.data[0]

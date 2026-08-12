import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(PROJECT_ROOT),
)

from chinaports_client import ChinaportsClientError, fetch_ship_info
from collection_repository import (
    create_collection_run,
    finish_collection_run,
    record_collection_item_failure,
    record_collection_item_success,
)
from latest_position_repository import get_latest_position_by_mmsi
from position_repository import upsert_position
from supabase_client import supabase
from vessel_repository import upsert_vessel


TRACKING_MODES = [
    "history_tracking",
    "high_risk_monitoring",
]


def parse_supabase_timestamp(value):
    if not value:
        return None

    normalized_value = str(value).replace(
        "Z",
        "+00:00",
    )

    return datetime.fromisoformat(
        normalized_value
    )


def is_within_monitoring_window(record, now):
    start_time = parse_supabase_timestamp(
        record.get("start_time")
    )
    end_time = parse_supabase_timestamp(
        record.get("end_time")
    )

    if start_time and start_time > now:
        return False

    if end_time and end_time <= now:
        return False

    return True


def get_active_tracking_records():
    result = (
        supabase
        .schema("tracking")
        .table("tracked_vessels")
        .select(
            "mmsi,tracking_mode,start_time,end_time,priority,"
            "tracking_interval_minutes"
        )
        .eq(
            "is_active",
            True,
        )
        .in_(
            "tracking_mode",
            TRACKING_MODES,
        )
        .order(
            "priority",
            desc=True,
        )
        .execute()
    )

    now = datetime.now(
        timezone.utc
    )

    return [
        record
        for record in result.data or []
        if record.get("mmsi")
        and is_within_monitoring_window(
            record,
            now,
        )
    ]


def update_collection_run_total(run_id, total_vessels):
    (
        supabase
        .schema("ingest")
        .table("collection_runs")
        .update(
            {
                "total_vessels": total_vessels,
            }
        )
        .eq(
            "id",
            run_id,
        )
        .execute()
    )


def process_vessel(record):
    mmsi = str(
        record["mmsi"]
    )

    print(
        f"Fetching vessel mmsi={mmsi} "
        f"mode={record.get('tracking_mode')} "
        f"priority={record.get('priority')}"
    )

    try:
        vessel_data = fetch_ship_info(
            mmsi
        )
    except ChinaportsClientError as exc:
        latest_position = get_latest_position_by_mmsi(
            mmsi
        )
        if latest_position:
            return {
                "mmsi": mmsi,
                "status": "skipped_existing_position",
                "reason": "chinaports_unavailable",
                "latest_position_id": latest_position.get("position_id"),
                "observed_at": latest_position.get("observed_at"),
            }

        raise RuntimeError(
            f"Chinaports unavailable and no latest position for mmsi={mmsi}: {exc}"
        ) from exc

    if not vessel_data:
        raise RuntimeError(
            f"Chinaports returned no data for mmsi={mmsi}."
        )

    vessel_result = upsert_vessel(
        vessel_data
    )
    position_result = upsert_position(
        vessel_data
    )

    return {
        "mmsi": mmsi,
        "vessel": vessel_result,
        "position": position_result,
    }


def main():
    run_id = create_collection_run()
    records = get_active_tracking_records()
    update_collection_run_total(
        run_id,
        len(records),
    )

    print(
        f"Active vessel tracking records: {len(records)}"
    )

    success_count = 0
    failed_count = 0

    for record in records:
        mmsi = record.get(
            "mmsi",
            "UNKNOWN",
        )

        try:
            result = process_vessel(
                record
            )
            success_count += 1
            record_collection_item_success(
                run_id,
                mmsi,
            )
            if result.get("status") == "skipped_existing_position":
                print(
                    "Skipped Chinaports refresh; using existing latest position "
                    f"mmsi={mmsi} observed_at={result.get('observed_at')}"
                )
            print(
                f"Success mmsi={mmsi}: {result}"
            )
        except Exception as exc:
            failed_count += 1
            record_collection_item_failure(
                run_id,
                mmsi,
                str(exc),
            )
            print(
                f"Failed mmsi={mmsi}: {exc}"
            )

    if failed_count == 0:
        status = "success"
    elif success_count == 0:
        status = "failed"
    else:
        status = "partial_failed"

    finish_collection_run(
        run_id,
        status,
        success_count,
        failed_count,
    )

    print(
        "Vessel position collection completed. "
        f"success={success_count}, failed={failed_count}"
    )


if __name__ == "__main__":
    main()

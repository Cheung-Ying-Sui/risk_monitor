import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(PROJECT_ROOT),
)

from risk_monitor.chinaports_client import ChinaportsClientError, fetch_ship_info
from risk_monitor.collection_repository import (
    create_collection_run,
    finish_collection_run,
    record_collection_item_failure,
    record_collection_item_success,
)
from risk_monitor.latest_position_repository import get_latest_position_by_mmsi
from risk_monitor.position_repository import upsert_position
from risk_monitor.supabase_client import supabase
from risk_monitor.vessel_repository import upsert_vessel
from risk_monitor.vessel_query_repository import get_vessel_by_mmsi
from risk_monitor.insurance_repository import InsuranceRepository
from risk_monitor.insurance_tracking_service import InsuranceTrackingService
from risk_monitor.insurance_voyage_lifecycle import VoyageLifecycleService
from risk_monitor.datalastic_client import is_configured as datalastic_is_configured


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


def process_vessel(record, insured_imos=None, insurance_service=None):
    mmsi = str(
        record["mmsi"]
    )

    print(
        f"Fetching vessel mmsi={mmsi} "
        f"mode={record.get('tracking_mode')} "
        f"priority={record.get('priority')}"
    )

    vessel = get_vessel_by_mmsi(mmsi)
    imo = str((vessel or {}).get("imo") or record.get("imo") or "").strip()
    if insured_imos and insurance_service:
        if imo in insured_imos:
            try:
                outcome = insurance_service.sync_imo(imo)
                if outcome == "tracking":
                    latest = get_latest_position_by_mmsi(mmsi)
                    if latest:
                        return {"mmsi": mmsi, "status": "insurance_ais_refreshed", "observed_at": latest.get("observed_at")}
            except Exception as exc:
                print(f"Insured AIS provider unavailable for IMO {imo}: {type(exc).__name__}; trying Chinaports")

    try:
        vessel_data = fetch_ship_info(imo=imo or None, mmsi=mmsi)
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

    if str(vessel_data.get("mmsi") or "") != mmsi or (imo and str(vessel_data.get("imo") or "") != imo):
        raise RuntimeError("Chinaports vessel identity mismatch; position was not saved.")

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
    insurance_service = InsuranceTrackingService() if datalastic_is_configured() else None
    voyage_lifecycle = VoyageLifecycleService()
    try:
        voyage_lifecycle.reconcile_finished()
    except Exception as exc:
        print(f"Insurance voyage reconciliation unavailable: {type(exc).__name__}: {exc}")
    try:
        insured_imos = {
            str(vessel.get("imo_number") or "").strip()
            for vessel in InsuranceRepository().list_insured_vessels()
        }
    except Exception as exc:
        print(f"Insurance vessel lookup unavailable: {type(exc).__name__}; using existing collector")
        insured_imos = set()
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
                record,
                insured_imos=insured_imos,
                insurance_service=insurance_service,
            )
            # Evaluate only an actual stored AIS observation. Lifecycle errors
            # must not turn a successful position collection into a failed one.
            try:
                vessel = get_vessel_by_mmsi(mmsi)
                imo = str((vessel or {}).get("imo") or "").strip()
                if imo in insured_imos:
                    latest = get_latest_position_by_mmsi(mmsi)
                    if latest:
                        ended = voyage_lifecycle.process_position(imo, latest)
                        if ended:
                            print(f"MVP voyage coverage ended for IMO {imo}: {ended}")
            except Exception as lifecycle_exc:
                print(f"Insurance voyage lifecycle unavailable mmsi={mmsi}: {type(lifecycle_exc).__name__}: {lifecycle_exc}")
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

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from risk_monitor.navigation.prediction_trigger import (  # noqa: E402
    refresh_prediction_after_position,
)
from risk_monitor.tracking_repository import get_tracked_vessels  # noqa: E402


def run_job(dry_run=False):
    started_at = datetime.now(timezone.utc).isoformat()
    records = get_tracked_vessels()
    results = []
    for record in records:
        vessel_id = record.get("vessel_id")
        mmsi = record.get("mmsi")
        if not vessel_id or not mmsi:
            results.append(
                {
                    "status": "skipped",
                    "vessel_id": vessel_id,
                    "mmsi": mmsi,
                    "reason": "missing_vessel_identity",
                }
            )
            continue
        if dry_run:
            results.append(
                {
                    "status": "planned",
                    "vessel_id": str(vessel_id),
                    "mmsi": str(mmsi),
                }
            )
            continue
        results.append(
            refresh_prediction_after_position(
                vessel_id=str(vessel_id),
                mmsi=str(mmsi),
            )
        )

    return {
        "started_at": started_at,
        "dry_run": bool(dry_run),
        "tracked_vessel_count": len(records),
        "updated_count": sum(
            result.get("status") == "updated" for result in results
        ),
        "failed_count": sum(
            result.get("status") == "failed" for result in results
        ),
        "skipped_count": sum(
            result.get("status") == "skipped" for result in results
        ),
        "results": results,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Refresh navigation predictions for active tracked vessels."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List eligible vessels without creating or updating predictions.",
    )
    args = parser.parse_args(argv)
    result = run_job(dry_run=args.dry_run)
    print(
        "Route prediction job completed. "
        f"dry_run={result['dry_run']} "
        f"tracked_vessel_count={result['tracked_vessel_count']} "
        f"updated_count={result['updated_count']} "
        f"failed_count={result['failed_count']} "
        f"skipped_count={result['skipped_count']}"
    )
    return 1 if result["failed_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

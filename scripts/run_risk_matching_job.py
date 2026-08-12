import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(PROJECT_ROOT),
)

from risk_repository import (  # noqa: E402
    get_tracked_vessels_in_risk_zones,
    record_current_risk_matches,
)
from tracking_repository import get_tracked_vessels  # noqa: E402


def _extract_inserted_count(record_result):
    if not isinstance(record_result, dict):
        raise ValueError("record_current_risk_matches returned non-dict result.")

    inserted_count = record_result.get("inserted_count")
    if inserted_count is None:
        raise ValueError("record_current_risk_matches missing inserted_count.")

    try:
        return int(inserted_count)
    except (TypeError, ValueError) as exc:
        raise ValueError("inserted_count must be an integer.") from exc


def run_job():
    run_time = datetime.now(timezone.utc).isoformat()

    active_tracked_vessels = get_tracked_vessels()
    matched_vessels = get_tracked_vessels_in_risk_zones()
    record_result = record_current_risk_matches()
    inserted_match_count = _extract_inserted_count(record_result)

    return {
        "run_time": run_time,
        "tracked_vessel_count": len(active_tracked_vessels),
        "matched_vessel_count": len(matched_vessels),
        "inserted_match_count": inserted_match_count,
        "errors": [],
    }


def main():
    try:
        result = run_job()
    except Exception as exc:
        print(
            "Risk matching job failed. "
            f"run_time={datetime.now(timezone.utc).isoformat()} "
            f"error={exc}"
        )
        return 1

    print(
        "Risk matching job completed. "
        f"run_time={result['run_time']} "
        f"tracked_vessel_count={result['tracked_vessel_count']} "
        f"matched_vessel_count={result['matched_vessel_count']} "
        f"inserted_match_count={result['inserted_match_count']} "
        f"errors={len(result['errors'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

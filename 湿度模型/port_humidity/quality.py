"""Coverage, continuity and value checks for a half-open UTC period."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from .time_utils import parse_utc, utc_iso

PASS_THRESHOLD = 0.995
FAIL_THRESHOLD = 0.95


def evaluate_quality(rows: list[dict[str, Any]], start: datetime, end: datetime,
                     *, duplicate_hours: int = 0, grid_distance_km: float | None = None,
                     grid_warning_km: float = 35) -> dict[str, Any]:
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise ValueError("quality period must use timezone-aware increasing timestamps")
    seconds = (end - start).total_seconds()
    if seconds % 3600:
        raise ValueError("quality period must cover whole UTC hours")
    expected = int(seconds // 3600)
    by_hour: dict[datetime, dict[str, Any]] = {}
    invalid = 0
    for row in rows:
        try:
            observed = parse_utc(str(row["observed_at_utc"]))
            if not start <= observed < end or observed.minute or observed.second or observed.microsecond:
                invalid += 1
                continue
            if observed in by_hour:
                duplicate_hours += 1
            by_hour[observed] = row
        except (KeyError, TypeError, ValueError):
            invalid += 1
    missing = [utc_iso(start + timedelta(hours=hour)) for hour in range(expected)
               if start + timedelta(hours=hour) not in by_hour]
    null_rh = 0
    complete = 0
    valid_rh = 0
    for row in by_hour.values():
        values = [row.get(name) for name in ("relative_humidity_pct", "temperature_2m_c", "dew_point_2m_c", "precipitation_mm")]
        rh = values[0]
        if rh is None:
            null_rh += 1
        if any(value is not None and (not isinstance(value, (int, float)) or not math.isfinite(value)) for value in values):
            invalid += 1
            continue
        if rh is not None and not 0 <= rh <= 100:
            invalid += 1
            continue
        if values[3] is not None and values[3] < 0:
            invalid += 1
            continue
        if rh is not None:
            valid_rh += 1
        if all(value is not None for value in values):
            complete += 1
    distinct = len(by_hour)
    coverage = distinct / expected if expected else 0
    rh_valid = valid_rh / expected if expected else 0
    grid_warning = grid_distance_km is not None and grid_distance_km > grid_warning_km
    if invalid or duplicate_hours or missing or complete < expected or coverage < FAIL_THRESHOLD or rh_valid < FAIL_THRESHOLD:
        status = "fail"
    elif coverage < PASS_THRESHOLD or rh_valid < PASS_THRESHOLD or grid_warning:
        status = "warn"
    else:
        status = "pass"
    return {
        "period_start_utc": utc_iso(start), "period_end_utc": utc_iso(end),
        "expected_hours": expected, "actual_distinct_hours": distinct,
        "complete_row_hours": complete, "missing_hours": len(missing),
        "null_rh_hours": null_rh, "invalid_value_hours": invalid,
        "completeness_ratio": round(coverage, 6), "rh_valid_ratio": round(rh_valid, 6),
        "status": status,
        "details": {"missing_timestamps_sample": missing[:50], "duplicate_hours": duplicate_hours,
                    "grid_distance_km": grid_distance_km, "grid_warning_km": grid_warning_km,
                    "grid_distance_warning": grid_warning, "pass_threshold": PASS_THRESHOLD},
    }


def grid_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance between requested analysis point and returned ERA5 grid point."""
    from math import asin, cos, radians, sin, sqrt
    a1, a2 = radians(lat1), radians(lat2)
    dlat, dlon = a2 - a1, radians(lon2 - lon1)
    value = sin(dlat / 2) ** 2 + cos(a1) * cos(a2) * sin(dlon / 2) ** 2
    return 6371.0088 * 2 * asin(min(1, sqrt(value)))

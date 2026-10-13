"""Monthly and calendar-day RH exposure, weighted by valid hourly observations."""

from __future__ import annotations

import calendar
from datetime import date
from threading import Lock
from time import monotonic
from typing import Any

from .profile import FIRST_YEAR, LAST_YEAR

_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}
_lock = Lock()
_TTL_SECONDS = 300


def _expected_hours(month: int, day: int | None = None) -> int:
    return 24 * sum(
        1 if day is not None else calendar.monthrange(year, month)[1]
        for year in range(FIRST_YEAR, LAST_YEAR + 1)
        if day is None or day <= calendar.monthrange(year, month)[1]
    )


def get_seasonal_humidity(repository: Any, *, port_code: str, month: int,
                          rh_threshold: float) -> dict[str, Any] | None:
    location = repository.primary_location(port_code)
    if location is None:
        return None
    source = repository.source()
    revision = repository.profile_revision(location["id"], source["id"])
    grid = ((revision["grid_latitude"], revision["grid_longitude"])
            if revision and revision.get("grid_latitude") is not None
            and revision.get("grid_longitude") is not None else None)
    key = (location["id"], source["id"], revision["ingested_at"] if revision else None,
           grid, month, rh_threshold, FIRST_YEAR, LAST_YEAR, "seasonal-v1")
    with _lock:
        cached = _cache.get(key)
        if cached and monotonic() - cached[0] < _TTL_SECONDS:
            return cached[1]

    rows = repository.chart_aggregates(location["id"], source["id"], grid, month, rh_threshold) if grid else []
    counts = {(row["bucket_type"], int(row["bucket_index"])): row for row in rows}

    def bucket(kind: str, index: int, expected: int) -> dict[str, Any]:
        row = counts.get((kind, index), {})
        valid = int(row.get("valid_hours") or 0)
        high = int(row.get("exceedance_hours") or 0)
        return {"index": index, "valid_hours": valid, "exceedance_hours": high,
                "expected_hours": expected, "percentage": round(100 * high / valid, 3) if valid else None}

    result = {
        "port_code": port_code, "location_id": location["id"],
        "month": month, "rh_threshold": rh_threshold,
        "historical_years": [FIRST_YEAR, LAST_YEAR], "timezone": "Asia/Shanghai",
        "monthly": [bucket("month", m, _expected_hours(m)) for m in range(1, 13)],
        "daily": [bucket("day", day, _expected_hours(month, day))
                  for day in range(1, calendar.monthrange(2024, month)[1] + 1)],
        "provenance": {"source": source["provider"], "model": source["dataset"],
                       "source_id": source["id"], "data_revision": revision["ingested_at"] if revision else None,
                       "grid_coordinates": {"latitude": grid[0], "longitude": grid[1]} if grid else None,
                       "method_version": "seasonal-v1"},
    }
    with _lock:
        if len(_cache) > 64:
            _cache.clear()
        _cache[key] = (monotonic(), result)
    return result

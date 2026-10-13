"""Server-side profile orchestration and revision-aware short-lived cache."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from threading import Lock
from time import monotonic
from typing import Any

from .profile import FIRST_YEAR, LAST_YEAR, METHOD_VERSION, WINDOW_DAYS, calculate_profile, historical_window
from .time_utils import SHANGHAI, UTC

_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}
_cache_lock = Lock()
_CACHE_TTL_SECONDS = 300


def get_humidity_profile(repository: Any, *, port_code: str, eta_date: date,
                         eta_time: time | None, rh_threshold: float) -> dict[str, Any] | None:
    location = repository.primary_location(port_code)
    if location is None:
        return None
    source = repository.source()
    revision = repository.profile_revision(location["id"], source["id"])
    grid = ((revision["grid_latitude"], revision["grid_longitude"])
            if revision and revision.get("grid_latitude") is not None and revision.get("grid_longitude") is not None
            else None)
    key = (location["id"], source["id"], revision["ingested_at"] if revision else None, grid,
           eta_date.month, eta_date.day, eta_time.hour if eta_time else None,
           rh_threshold, FIRST_YEAR, LAST_YEAR, WINDOW_DAYS, METHOD_VERSION)
    with _cache_lock:
        cached = _cache.get(key)
        if cached and monotonic() - cached[0] < _CACHE_TTL_SECONDS:
            result = {**cached[1], "scope": {**cached[1]["scope"], "eta_date": eta_date.isoformat()}}
            return result

    yearly_rows: dict[int, list[dict[str, Any]]] = {}
    if revision:
        for year in range(FIRST_YEAR, LAST_YEAR + 1):
            window = historical_window(year, eta_date.month, eta_date.day)
            if window is None:
                continue
            # Seven extra calendar days on both sides provide event context. Runs still
            # touching the fetched edge are censored, never treated as complete.
            context_start = window[0] - timedelta(days=7)
            context_end = window[1] + timedelta(days=8)
            start_utc = datetime.combine(context_start, time.min, SHANGHAI).astimezone(UTC)
            end_utc = datetime.combine(context_end, time.min, SHANGHAI).astimezone(UTC)
            yearly_rows[year] = repository.profile_rows(location["id"], source["id"], start_utc, end_utc)

    result = calculate_profile(eta_date=eta_date, eta_time=eta_time, threshold=rh_threshold,
                               yearly_rows=yearly_rows, expected_grid=grid)
    result["location_id"] = location["id"]
    result["port_code"] = port_code
    result["provenance"] = {
        "source": source["provider"], "model": source["dataset"], "source_id": source["id"],
        "coordinate_status": location["verification_status"],
        "coordinate_source": location.get("coordinate_source"),
        "requested_coordinates": {"latitude": location.get("requested_latitude"),
                                  "longitude": location.get("requested_longitude")},
        "grid_coordinates": {"latitude": grid[0], "longitude": grid[1]} if grid else None,
        "data_revision": revision["ingested_at"] if revision else None,
        "method_version": METHOD_VERSION,
    }
    with _cache_lock:
        if len(_cache) > 64:
            _cache.clear()
        _cache[key] = (monotonic(), result)
    return result

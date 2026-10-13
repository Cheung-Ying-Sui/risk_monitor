"""Reproducible historical RH exposure statistics (Shanghai local calendar)."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta
from math import isfinite
from statistics import mean
from typing import Any

from .time_utils import SHANGHAI, UTC, parse_utc

METHOD_VERSION = "phase2-v1"
FIRST_YEAR = 2016
LAST_YEAR = 2025
WINDOW_DAYS = 7
MIN_YEAR_COVERAGE = 0.95


def percentile_cont(values: list[float], fraction: float = 0.9) -> float | None:
    """PostgreSQL percentile_cont-compatible linear interpolation."""
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lower = int(index)
    return ordered[lower] + (ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower]) * (index - lower)


def historical_window(year: int, month: int, day: int, days: int = WINDOW_DAYS) -> tuple[date, date] | None:
    try:
        center = date(year, month, day)
    except ValueError:
        return None
    return center - timedelta(days=days), center + timedelta(days=days)


def _valid_rh(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        return None
    result = float(value)
    return result if isfinite(result) and 0 <= result <= 100 else None


def _timestamp(value: str | datetime) -> datetime:
    return parse_utc(value) if isinstance(value, str) else value.astimezone(UTC)


def calculate_profile(
    *, eta_date: date, eta_time: time | None, threshold: float,
    yearly_rows: dict[int, list[dict[str, Any]]], window_days: int = WINDOW_DAYS,
    first_year: int = FIRST_YEAR, last_year: int = LAST_YEAR,
    expected_grid: tuple[float, float] | None = None,
) -> dict[str, Any]:
    """Calculate using bounded per-year rows containing the window and event context."""
    if not 0 <= threshold <= 100 or window_days != WINDOW_DAYS:
        raise ValueError("invalid threshold or window")
    if eta_time is not None and (eta_time.minute or eta_time.second or eta_time.microsecond):
        raise ValueError("ETA time must be a whole hour")

    requested_years = list(range(first_year, last_year + 1))
    valid_years: list[int] = []
    excluded_years: list[dict[str, Any]] = []
    date_ranges: list[dict[str, Any]] = []
    all_rh: list[float] = []
    event_lengths: list[float] = []
    censored_count = 0
    duplicate_count = 0
    grid_mismatch_count = 0
    expected_hours = 0
    valid_hours = 0
    eta_success = eta_valid = eta_excluded = 0

    for year in requested_years:
        window = historical_window(year, eta_date.month, eta_date.day, window_days)
        if window is None:  # Feb 29 in non-leap years is never shifted to Mar 1.
            excluded_years.append({"year": year, "reason": "invalid_calendar_date"})
            continue
        start_date, end_date = window
        date_ranges.append({"year": year, "start": start_date.isoformat(), "end": end_date.isoformat()})
        start = datetime.combine(start_date, time.min, SHANGHAI).astimezone(UTC)
        end = datetime.combine(end_date + timedelta(days=1), time.min, SHANGHAI).astimezone(UTC)
        expected = (end - start) // timedelta(hours=1)
        expected_hours += expected

        raw = yearly_rows.get(year, [])
        counts = Counter(_timestamp(row["observed_at_utc"]) for row in raw)
        duplicate_count += sum(n - 1 for n in counts.values() if n > 1)
        points: dict[datetime, float | None] = {}
        for row in raw:
            stamp = _timestamp(row["observed_at_utc"])
            if counts[stamp] != 1:
                points[stamp] = None
                continue
            if expected_grid is not None:
                grid = (row.get("grid_latitude"), row.get("grid_longitude"))
                if grid != expected_grid:
                    grid_mismatch_count += 1
                    points[stamp] = None
                    continue
            points[stamp] = _valid_rh(row.get("relative_humidity_pct"))

        window_stamps = [start + timedelta(hours=hour) for hour in range(expected)]
        year_rh = [points[stamp] for stamp in window_stamps if points.get(stamp) is not None]
        coverage = len(year_rh) / expected
        if coverage < MIN_YEAR_COVERAGE:
            excluded_years.append({"year": year, "reason": "low_coverage", "valid_hours": len(year_rh),
                                   "expected_hours": expected, "coverage_fraction": coverage})
            continue
        valid_years.append(year)
        valid_hours += len(year_rh)
        all_rh.extend(year_rh)

        # Detect runs over the complete fetched context, not a truncated 15-day window.
        sorted_stamps = sorted(points)
        runs: list[tuple[datetime, int, bool]] = []
        run_start: datetime | None = None
        run_length = 0
        previous: datetime | None = None
        for stamp in sorted_stamps:
            rh = points[stamp]
            if run_start is not None and (stamp - previous != timedelta(hours=1) or rh is None or rh < threshold):
                runs.append((run_start, run_length, previous == sorted_stamps[-1]))
                run_start, run_length = None, 0
            if rh is not None and rh >= threshold:
                if run_start is None:
                    run_start, run_length = stamp, 0
                run_length += 1
            previous = stamp
        if run_start is not None:
            runs.append((run_start, run_length, True))

        for run_start, length, touches_end in runs:
            if length < 3 or not start <= run_start < end:
                continue
            if run_start == sorted_stamps[0] or touches_end:
                censored_count += 1
                continue
            event_lengths.append(float(length))

        if eta_time is not None:
            for local_day_offset in range((end_date - start_date).days + 1):
                local_day = start_date + timedelta(days=local_day_offset)
                eta_start = datetime.combine(local_day, eta_time, SHANGHAI).astimezone(UTC)
                values = [points.get(eta_start + timedelta(hours=hour)) for hour in range(24)]
                if any(value is None for value in values):
                    eta_excluded += 1
                    continue
                eta_valid += 1
                consecutive = 0
                success = False
                for value in values:
                    consecutive = consecutive + 1 if value >= threshold else 0
                    if consecutive >= 6:
                        success = True
                        break
                eta_success += int(success)

    warnings: list[str] = []
    if excluded_years:
        warnings.append("部分历史年份因日期不存在或有效RH覆盖率不足95%而排除")
    if len(valid_years) < 5:
        warnings.append("有效历史年份少于5年，结果仅供探索")
    if censored_count:
        warnings.append("有无法确认完整起止的高湿度事件，已从事件统计中排除")
    if duplicate_count or grid_mismatch_count:
        warnings.append("重复时间戳或ERA5网格不一致的记录已排除")
    if eta_time is not None and eta_valid < 30:
        warnings.append("ETA 24小时有效窗口少于30个，样本有限且窗口相互重叠")

    metrics = {
        "mean_rh": mean(all_rh) if all_rh else None,
        "p90_rh": percentile_cont(all_rh),
        "exceedance_fraction": sum(rh >= threshold for rh in all_rh) / len(all_rh) if all_rh else None,
        "event_mean_hours": mean(event_lengths) if event_lengths else None,
        "event_p90_hours": percentile_cont(event_lengths),
        "events_per_year": len(event_lengths) / len(valid_years) if valid_years else None,
    }
    return {
        "scope": {"eta_date": eta_date.isoformat(), "eta_time": eta_time.strftime("%H:%M") if eta_time else None,
                  "timezone": "Asia/Shanghai", "window_days": window_days, "rh_threshold": threshold,
                  "historical_years_requested": [first_year, last_year], "historical_years_used": valid_years,
                  "window_semantics": "year-local ±7 calendar days", "date_ranges": date_ranges},
        "metrics": metrics,
        "eta_24h": ({"continuous_6h_frequency": eta_success / eta_valid if eta_valid else None,
                     "success_count": eta_success, "valid_window_count": eta_valid,
                     "excluded_window_count": eta_excluded} if eta_time is not None else None),
        "quality": {"valid_hour_count": valid_hours, "expected_hour_count": expected_hours,
                    "coverage_fraction": valid_hours / expected_hours if expected_hours else None,
                    "valid_year_count": len(valid_years), "excluded_years": excluded_years,
                    "censored_event_count": censored_count, "duplicate_hour_count": duplicate_count,
                    "grid_mismatch_count": grid_mismatch_count, "warnings": warnings},
    }

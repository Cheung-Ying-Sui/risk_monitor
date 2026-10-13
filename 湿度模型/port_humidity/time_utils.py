"""UTC-only calendar calculations for hourly ERA5 ingestion."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
SHANGHAI = ZoneInfo("Asia/Shanghai")


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("UTC timestamp must include a timezone")
    return parsed.astimezone(UTC)


def utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("UTC timestamp must include a timezone")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def shanghai_iso(value: str | datetime) -> str:
    observed = parse_utc(value) if isinstance(value, str) else value
    if observed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return observed.astimezone(SHANGHAI).isoformat()


def expected_hours(start_date: date, end_date: date) -> int:
    if end_date < start_date:
        raise ValueError("end date precedes start date")
    return (end_date - start_date).days * 24 + 24


def month_chunks(start_date: date, end_date: date):
    if end_date < start_date:
        raise ValueError("end date precedes start date")
    cursor = start_date
    while cursor <= end_date:
        month_end = date(cursor.year, cursor.month, calendar.monthrange(cursor.year, cursor.month)[1])
        chunk_end = min(month_end, end_date)
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(days=1)


def period_bounds(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    return datetime.combine(start_date, datetime.min.time(), UTC), datetime.combine(end_date + timedelta(days=1), datetime.min.time(), UTC)


def shanghai_period_bounds(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    """Inclusive Shanghai calendar dates as a half-open UTC interval."""
    if end_date < start_date:
        raise ValueError("end date precedes start date")
    return (datetime.combine(start_date, datetime.min.time(), SHANGHAI).astimezone(UTC),
            datetime.combine(end_date + timedelta(days=1), datetime.min.time(), SHANGHAI).astimezone(UTC))

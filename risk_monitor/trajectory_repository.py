from datetime import datetime, timedelta, timezone

from risk_monitor.supabase_client import supabase


TRACK_POINT_FIELDS = (
    "mmsi,latitude,longitude,sog,cog,heading,destination,nav_status,"
    "observed_at,received_at,source_id"
)


def _normalize_limit(limit):
    try:
        normalized_limit = int(limit)
    except (TypeError, ValueError):
        raise ValueError("limit must be an integer.")

    if normalized_limit <= 0:
        raise ValueError("limit must be greater than 0.")

    return normalized_limit


def _normalize_hours(hours):
    try:
        normalized_hours = float(hours)
    except (TypeError, ValueError):
        raise ValueError("hours must be numeric.")

    if normalized_hours <= 0:
        raise ValueError("hours must be greater than 0.")

    return normalized_hours


def _normalize_mmsi(mmsi):
    if not mmsi:
        raise ValueError("mmsi is required.")

    normalized_mmsi = str(mmsi).strip()
    if not normalized_mmsi:
        raise ValueError("mmsi is required.")

    return normalized_mmsi


def get_vessel_track(mmsi, limit=500):
    result = (
        supabase
        .schema("tracking")
        .table("vessel_positions")
        .select(TRACK_POINT_FIELDS)
        .eq(
            "mmsi",
            _normalize_mmsi(mmsi),
        )
        .order(
            "observed_at",
            desc=False,
        )
        .limit(_normalize_limit(limit))
        .execute()
    )

    return result.data or []


def get_recent_track_points(mmsi, hours=24):
    since_timestamp = (
        datetime.now(timezone.utc)
        - timedelta(hours=_normalize_hours(hours))
    ).isoformat()

    result = (
        supabase
        .schema("tracking")
        .table("vessel_positions")
        .select(TRACK_POINT_FIELDS)
        .eq(
            "mmsi",
            _normalize_mmsi(mmsi),
        )
        .gte(
            "observed_at",
            since_timestamp,
        )
        .order(
            "observed_at",
            desc=False,
        )
        .execute()
    )

    return result.data or []


def get_latest_track_point(mmsi):
    result = (
        supabase
        .schema("tracking")
        .table("vessel_positions")
        .select(TRACK_POINT_FIELDS)
        .eq(
            "mmsi",
            _normalize_mmsi(mmsi),
        )
        .order(
            "observed_at",
            desc=True,
        )
        .limit(1)
        .execute()
    )

    if not result.data:
        return None

    return result.data[0]

import re
from datetime import datetime, timedelta, timezone

from risk_monitor.supabase_client import supabase


def clean_val(value):
    if (
        value is None
        or str(value).lower() == "null"
        or str(value).strip() == ""
        or str(value) == "--"
    ):
        return None

    return value


def parse_timestamp(timestamp_value):
    timestamp_value = clean_val(timestamp_value)
    if not timestamp_value:
        return datetime.now(timezone.utc).isoformat()

    try:
        timestamp_text = str(timestamp_value)
        timezone_match = re.search(
            r"\(UTC([+-]\d{1,2})\)",
            timestamp_text,
            re.IGNORECASE,
        )
        clean_timestamp = re.sub(r"\(.*?\)", "", timestamp_text).strip()

        for timestamp_format in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
        ):
            try:
                parsed_timestamp = datetime.strptime(
                    clean_timestamp,
                    timestamp_format,
                )

                if timezone_match:
                    offset_hours = int(timezone_match.group(1))
                    source_timezone = timezone(
                        timedelta(hours=offset_hours)
                    )
                    return (
                        parsed_timestamp
                        .replace(tzinfo=source_timezone)
                        .astimezone(timezone.utc)
                        .isoformat()
                    )

                return parsed_timestamp.replace(
                    tzinfo=timezone.utc
                ).isoformat()
            except ValueError:
                continue
    except Exception:
        pass

    return datetime.now(timezone.utc).isoformat()


def parse_coordinate(coordinate_value):
    coordinate_value = clean_val(coordinate_value)
    if not coordinate_value:
        return None

    match = re.search(
        r"([NESW])\s*(\d+)度(\d+\.\d+)分",
        str(coordinate_value),
    )
    if not match:
        return None

    direction, degrees, minutes = match.groups()
    decimal_degrees = float(degrees) + float(minutes) / 60.0

    if direction in [
        "S",
        "W",
    ]:
        decimal_degrees *= -1

    return decimal_degrees


def to_numeric(value):
    value = clean_val(value)
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_vessel_id(mmsi):
    result = (
        supabase
        .schema("core")
        .table("vessels")
        .select("id")
        .eq(
            "mmsi",
            str(mmsi),
        )
        .limit(1)
        .execute()
    )

    if not result.data:
        raise ValueError(
            f"Vessel with mmsi={mmsi} does not exist in core.vessels."
        )

    return result.data[0]["id"]


def get_chinaports_source_id():
    result = (
        supabase
        .schema("ingest")
        .table("data_sources")
        .select("id")
        .eq(
            "source_code",
            "CHINAPORTS",
        )
        .limit(1)
        .execute()
    )

    if not result.data:
        raise ValueError(
            "Data source CHINAPORTS does not exist in ingest.data_sources."
        )

    return result.data[0]["id"]


def upsert_position(raw_data):
    if not raw_data:
        raise ValueError("raw_data is required.")

    mmsi = clean_val(raw_data.get("mmsi"))
    if not mmsi:
        raise ValueError("raw_data.mmsi is required.")

    vessel_id = get_vessel_id(mmsi)
    source_id = get_chinaports_source_id()

    payload = {
        "vessel_id": vessel_id,
        "source_id": source_id,
        "mmsi": str(mmsi),
        "latitude": parse_coordinate(raw_data.get("latitude")),
        "longitude": parse_coordinate(raw_data.get("longitude")),
        "heading": to_numeric(raw_data.get("trueHeading")),
        "cog": to_numeric(raw_data.get("cog")),
        "sog": to_numeric(raw_data.get("sog")),
        "eta": clean_val(raw_data.get("eta")),
        "destination": clean_val(raw_data.get("destination")),
        "draught": to_numeric(raw_data.get("draught")),
        "nav_status": clean_val(raw_data.get("navStatus")),
        "observed_at": parse_timestamp(raw_data.get("timeStamp")),
    }

    result = (
        supabase
        .schema("tracking")
        .table("vessel_positions")
        .upsert(
            payload,
            on_conflict="vessel_id,observed_at,source_id",
        )
        .execute()
    )

    return result.data

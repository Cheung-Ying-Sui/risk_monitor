import logging
import re
from datetime import datetime, timedelta, timezone

from risk_monitor.supabase_client import supabase
from risk_monitor.navigation.prediction_trigger import (
    refresh_prediction_after_position,
)


logger = logging.getLogger(__name__)


def _refresh_navigation_prediction_safely(payload, persisted_rows):
    if not persisted_rows:
        return None

    try:
        return refresh_prediction_after_position(
            vessel_id=payload.get("vessel_id"),
            mmsi=payload.get("mmsi"),
            observed_at=payload.get("observed_at"),
        )
    except Exception:
        logger.exception(
            "navigation_prediction_trigger_failed_after_ais_persistence "
            "vessel_id=%s mmsi=%s observed_at=%s",
            payload.get("vessel_id"),
            payload.get("mmsi"),
            payload.get("observed_at"),
        )
        return None


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


def _require_valid_latitude(value):
    latitude = to_numeric(value)
    if latitude is None or latitude < -90 or latitude > 90:
        raise ValueError("position_data.latitude is invalid.")

    return latitude


def _require_valid_longitude(value):
    longitude = to_numeric(value)
    if longitude is None or longitude < -180 or longitude > 180:
        raise ValueError("position_data.longitude is invalid.")

    return longitude


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


def upsert_position_for_vessel(vessel_id, mmsi, position_data, source_code="CHINAPORTS"):
    if not vessel_id:
        raise ValueError("vessel_id is required.")
    if not mmsi:
        raise ValueError("mmsi is required.")
    if not position_data:
        raise ValueError("position_data is required.")

    observed_at = clean_val(position_data.get("observed_at"))
    if not observed_at:
        raise ValueError("position_data.observed_at is required.")

    if source_code == "CHINAPORTS":
        source_id = get_chinaports_source_id()
    elif source_code == "DATALASTIC":
        source_result = (
            supabase.schema("ingest").table("data_sources")
            .upsert({"source_code": "DATALASTIC", "source_name": "Datalastic AIS API", "source_type": "api"}, on_conflict="source_code")
            .execute()
        )
        if not source_result.data:
            raise RuntimeError("Datalastic data source registration failed.")
        source_id = source_result.data[0]["id"]
    else:
        raise ValueError("Unsupported AIS source code.")

    payload = {
        "vessel_id": str(vessel_id),
        "source_id": source_id,
        "mmsi": str(mmsi),
        "latitude": _require_valid_latitude(position_data.get("latitude")),
        "longitude": _require_valid_longitude(position_data.get("longitude")),
        "heading": to_numeric(position_data.get("heading")),
        "cog": to_numeric(position_data.get("cog")),
        "sog": to_numeric(position_data.get("sog")),
        "destination": clean_val(position_data.get("destination")),
        "nav_status": clean_val(
            position_data.get(
                "navigation_status",
                position_data.get("nav_status"),
            )
        ),
        "observed_at": observed_at,
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

    _refresh_navigation_prediction_safely(payload, result.data)
    return result.data


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

    _refresh_navigation_prediction_safely(payload, result.data)
    return result.data

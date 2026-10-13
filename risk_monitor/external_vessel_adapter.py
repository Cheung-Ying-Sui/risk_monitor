import re
from datetime import datetime, timedelta, timezone
from typing import Any


EXTERNAL_SOURCE_CHINAPORTS = "chinaports"


def clean_value(value: Any) -> Any:
    if value is None:
        return None

    text = str(value).strip()
    if not text or text.lower() == "null" or text == "--":
        return None

    return value


def clean_string(value: Any) -> str | None:
    value = clean_value(value)
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    return text


def normalize_imo(value: Any) -> str | None:
    text = clean_string(value)
    if text is None:
        return None

    if text == "0":
        return None

    return text


def normalize_mmsi(value: Any) -> str | None:
    return clean_string(value)


def to_float(value: Any) -> float | None:
    value = clean_value(value)
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_coordinate(value: Any) -> float | None:
    value = clean_value(value)
    if value is None:
        return None

    if isinstance(value, int | float):
        return float(value)

    text = str(value).strip()
    try:
        return float(text)
    except ValueError:
        pass

    match = re.search(
        r"([NESW])\s*(\d+)度(\d+(?:\.\d+)?)分",
        text,
    )
    if not match:
        return None

    direction, degrees, minutes = match.groups()
    coordinate = float(degrees) + float(minutes) / 60.0
    if direction in {"S", "W"}:
        coordinate *= -1

    return coordinate


def valid_latitude(value: float | None) -> bool:
    return value is not None and -90 <= value <= 90


def valid_longitude(value: float | None) -> bool:
    return value is not None and -180 <= value <= 180


def normalize_timestamp(value: Any) -> str | None:
    value = clean_value(value)
    if value is None:
        return None

    if isinstance(value, datetime):
        timestamp = value
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc).isoformat()

    text = str(value).strip()
    try:
        timestamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc).isoformat()
    except ValueError:
        pass

    timezone_match = re.search(
        r"\(UTC([+-]\d{1,2})\)",
        text,
        re.IGNORECASE,
    )
    clean_timestamp = re.sub(r"\(.*?\)", "", text).strip()
    for timestamp_format in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ):
        try:
            timestamp = datetime.strptime(
                clean_timestamp,
                timestamp_format,
            )
        except ValueError:
            continue

        if timezone_match:
            source_timezone = timezone(
                timedelta(hours=int(timezone_match.group(1)))
            )
            timestamp = timestamp.replace(tzinfo=source_timezone)
        else:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        return timestamp.astimezone(timezone.utc).isoformat()

    return None


def _first_value(data: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = clean_value(data.get(key))
        if value is not None:
            return value

    return None


def normalize_latest_position(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not data:
        return None

    latitude = parse_coordinate(_first_value(data, ["latitude", "lat"]))
    longitude = parse_coordinate(_first_value(data, ["longitude", "lon", "lng"]))
    observed_at = normalize_timestamp(
        _first_value(data, ["observed_at", "timeStamp"])
    )

    if not valid_latitude(latitude) or not valid_longitude(longitude):
        return None

    if not observed_at:
        return None

    return {
        "latitude": latitude,
        "longitude": longitude,
        "sog": to_float(_first_value(data, ["sog"])),
        "cog": to_float(_first_value(data, ["cog"])),
        "heading": to_float(_first_value(data, ["heading", "trueHeading"])),
        "navigation_status": clean_string(
            _first_value(data, ["navigation_status", "nav_status", "navStatus"])
        ),
        "destination": clean_string(_first_value(data, ["destination"])),
        "observed_at": observed_at,
    }


def normalize_chinaports_vessel(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not data:
        return None

    mmsi = normalize_mmsi(_first_value(data, ["mmsi", "MMSI"]))
    name = clean_string(
        _first_value(data, ["ship_name", "shipname", "shipName", "name"])
    )
    if not mmsi or not name:
        return None

    return {
        "source": "external",
        "external_source": EXTERNAL_SOURCE_CHINAPORTS,
        "is_persisted": False,
        "id": None,
        "mmsi": mmsi,
        "imo": normalize_imo(_first_value(data, ["imo", "IMO"])),
        "name": name,
        "callsign": clean_string(
            _first_value(data, ["callsign", "callSign", "call_sign"])
        ),
        "ship_type": clean_string(
            _first_value(data, ["ship_type", "shipType", "shiptype"])
        ),
        "flag_state": clean_string(
            _first_value(data, ["flag_state", "flagState", "flag", "shipCountry"])
        ),
        "length_m": to_float(_first_value(data, ["length_m", "length"])),
        "width_m": to_float(_first_value(data, ["width_m", "width"])),
        "gross_tonnage": to_float(
            _first_value(data, ["gross_tonnage", "ship_all_dun", "shipAllDun"])
        ),
        "is_tracked": False,
        "latest_position": normalize_latest_position(data),
    }


def normalize_onboard_candidate(data: dict[str, Any]) -> dict[str, Any]:
    latest_position = normalize_latest_position(data.get("latest_position"))

    return {
        "source": clean_string(data.get("source")) or EXTERNAL_SOURCE_CHINAPORTS,
        "mmsi": normalize_mmsi(data.get("mmsi")),
        "imo": normalize_imo(data.get("imo")),
        "name": clean_string(data.get("name")),
        "callsign": clean_string(data.get("callsign")),
        "ship_type": clean_string(data.get("ship_type")),
        "flag_state": clean_string(data.get("flag_state")),
        "length_m": to_float(data.get("length_m")),
        "width_m": to_float(data.get("width_m")),
        "gross_tonnage": to_float(data.get("gross_tonnage")),
        "latest_position": latest_position,
    }

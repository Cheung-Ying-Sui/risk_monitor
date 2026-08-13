from risk_monitor.chinaports_client import fetch_ship_info
from risk_monitor.latest_position_repository import get_latest_position_by_mmsi
from risk_monitor.position_repository import parse_coordinate, parse_timestamp, to_numeric
from risk_monitor.vessel_query_repository import get_vessel_by_imo, get_vessel_by_mmsi


def _clean_value(value):
    if value is None:
        return None

    text = str(value).strip()
    if not text or text.lower() == "null" or text == "--":
        return None

    return value


def _first_value(data, keys):
    for key in keys:
        value = _clean_value(data.get(key))
        if value is not None:
            return value

    return None


def _normalize_live_vessel(raw_data):
    if not raw_data:
        return None

    return {
        "mmsi": _first_value(raw_data, ["mmsi", "MMSI"]),
        "imo": _first_value(raw_data, ["imo", "IMO"]),
        "ship_name": _first_value(
            raw_data,
            ["ship_name", "shipname", "shipName", "name"],
        ),
        "callsign": _first_value(
            raw_data,
            ["callsign", "callSign", "call_sign"],
        ),
        "ship_type": _first_value(
            raw_data,
            ["ship_type", "shipType", "shiptype"],
        ),
        "flag_state": _first_value(
            raw_data,
            ["flag_state", "flagState", "flag"],
        ),
        "length_m": to_numeric(
            _first_value(raw_data, ["length_m", "length"])
        ),
        "width_m": to_numeric(
            _first_value(raw_data, ["width_m", "width"])
        ),
        "gross_tonnage": to_numeric(
            _first_value(
                raw_data,
                ["gross_tonnage", "ship_all_dun", "shipAllDun"],
            )
        ),
        "latitude": parse_coordinate(
            _first_value(raw_data, ["latitude", "lat"])
        ),
        "longitude": parse_coordinate(
            _first_value(raw_data, ["longitude", "lon", "lng"])
        ),
        "sog": to_numeric(_first_value(raw_data, ["sog"])),
        "cog": to_numeric(_first_value(raw_data, ["cog"])),
        "heading": to_numeric(
            _first_value(raw_data, ["heading", "trueHeading"])
        ),
        "destination": _first_value(raw_data, ["destination"]),
        "nav_status": _first_value(
            raw_data,
            ["nav_status", "navStatus"],
        ),
        "observed_at": parse_timestamp(
            _first_value(raw_data, ["observed_at", "timeStamp"])
        ),
        "raw_data": raw_data,
    }


def _merge_latest_position(vessel, source="supabase", warning=None):
    if not vessel or not vessel.get("mmsi"):
        return vessel

    latest_position = get_latest_position_by_mmsi(vessel["mmsi"])
    metadata = {
        "dashboard_source": source,
    }
    if warning:
        metadata["dashboard_warning"] = warning

    if not latest_position:
        return {
            **vessel,
            **metadata,
            "raw_data": vessel.get("raw_data") or vessel,
        }

    return {
        **vessel,
        **{
            key: value
            for key, value in latest_position.items()
            if value is not None
        },
        **metadata,
        "raw_data": vessel.get("raw_data") or vessel,
    }


def _search_vessel_from_supabase(query, search_type, warning=None):
    if search_type == "imo":
        vessel = get_vessel_by_imo(query)
    else:
        vessel = get_vessel_by_mmsi(query)

    if not vessel:
        return None

    return _merge_latest_position(
        vessel,
        source="supabase",
        warning=warning,
    )


def search_vessel_live(query, search_type="mmsi"):
    normalized_query = str(query or "").strip()
    if not normalized_query:
        raise ValueError("query is required.")

    normalized_search_type = str(search_type or "").strip().lower()
    if normalized_search_type not in {"mmsi", "imo"}:
        raise ValueError("search_type must be mmsi or imo.")

    cached_vessel = _search_vessel_from_supabase(
        normalized_query,
        normalized_search_type,
    )
    if cached_vessel:
        return cached_vessel

    try:
        raw_data = fetch_ship_info(normalized_query)
        vessel = _normalize_live_vessel(raw_data)
    except Exception as exc:
        return _search_vessel_from_supabase(
            normalized_query,
            normalized_search_type,
            warning=str(exc),
        )

    if not vessel or not vessel.get("mmsi"):
        return _search_vessel_from_supabase(
            normalized_query,
            normalized_search_type,
            warning="Chinaports returned no usable vessel data.",
        )

    return _merge_latest_position(
        vessel,
        source="chinaports",
    )

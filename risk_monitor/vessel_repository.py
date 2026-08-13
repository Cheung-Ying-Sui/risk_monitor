from risk_monitor.supabase_client import supabase


def _clean_value(value):
    if value is None:
        return None

    text = str(value).strip()
    if not text or text.lower() == "null" or text == "--":
        return None

    return value


def _to_numeric(value):
    value = _clean_value(value)
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def upsert_vessel(vessel_data):
    if not vessel_data:
        raise ValueError("vessel_data is required.")

    mmsi = _clean_value(vessel_data.get("mmsi"))
    if not mmsi:
        raise ValueError("vessel_data.mmsi is required.")

    payload = {
        "mmsi": str(mmsi),
        "imo": _clean_value(vessel_data.get("imo")),
        "ship_name": _clean_value(
            vessel_data.get("ship_name", vessel_data.get("shipname"))
        ),
        "callsign": _clean_value(vessel_data.get("callsign")),
        "length_m": _to_numeric(
            vessel_data.get("length_m", vessel_data.get("length"))
        ),
        "width_m": _to_numeric(
            vessel_data.get("width_m", vessel_data.get("width"))
        ),
        "gross_tonnage": _to_numeric(
            vessel_data.get(
                "gross_tonnage",
                vessel_data.get(
                    "ship_all_dun",
                    vessel_data.get("shipAllDun"),
                ),
            )
        ),
    }

    result = (
        supabase
        .schema("core")
        .table("vessels")
        .upsert(
            payload,
            on_conflict="mmsi",
        )
        .execute()
    )

    return result.data

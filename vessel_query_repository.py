from supabase_client import supabase


VESSEL_FIELDS = (
    "mmsi,imo,ship_name,callsign,ship_type,flag_state,"
    "length_m,width_m,gross_tonnage"
)

LATEST_POSITION_FIELDS = (
    "vessel_id,mmsi,latitude,longitude,sog,cog,heading,"
    "destination,nav_status,observed_at,received_at,source_id"
)


def _normalize_identifier(value, field_name):
    if not value:
        raise ValueError(f"{field_name} is required.")

    normalized_value = str(value).strip()
    if not normalized_value:
        raise ValueError(f"{field_name} is required.")

    return normalized_value


def get_vessel_by_mmsi(mmsi):
    normalized_mmsi = _normalize_identifier(
        mmsi,
        "mmsi",
    )

    result = (
        supabase
        .schema("core")
        .table("vessels")
        .select(VESSEL_FIELDS)
        .eq(
            "mmsi",
            normalized_mmsi,
        )
        .limit(1)
        .execute()
    )

    if not result.data:
        return None

    return result.data[0]


def get_vessel_by_imo(imo):
    normalized_imo = _normalize_identifier(
        imo,
        "imo",
    )

    result = (
        supabase
        .schema("core")
        .table("vessels")
        .select(VESSEL_FIELDS)
        .eq(
            "imo",
            normalized_imo,
        )
        .limit(1)
        .execute()
    )

    if not result.data:
        return None

    return result.data[0]


def get_vessel_current_status(mmsi):
    normalized_mmsi = _normalize_identifier(
        mmsi,
        "mmsi",
    )
    vessel = get_vessel_by_mmsi(normalized_mmsi)
    if not vessel:
        return None

    position_result = (
        supabase
        .schema("tracking")
        .table("latest_vessel_positions")
        .select(LATEST_POSITION_FIELDS)
        .eq(
            "mmsi",
            normalized_mmsi,
        )
        .limit(1)
        .execute()
    )

    latest_position = None
    if position_result.data:
        latest_position = position_result.data[0]

    return {
        **vessel,
        "latest_position": latest_position,
    }

from supabase_client import supabase


ACTIVE_RISK_ZONE_FIELDS = (
    "zone_id,zone_version_id,zone_name,zone_slug,zone_type,source,"
    "source_document,effective_date,confidence"
)


ACTIVE_RISK_ZONE_GEOJSON_FIELDS = (
    "zone_id,zone_version_id,zone_name,zone_type,source,"
    "source_document,effective_date,geometry_geojson"
)


def _normalize_mmsi(mmsi):
    if not mmsi:
        raise ValueError("mmsi is required.")

    normalized_mmsi = str(mmsi).strip()
    if not normalized_mmsi:
        raise ValueError("mmsi is required.")

    return normalized_mmsi


def get_active_risk_zones():
    result = (
        supabase
        .schema("tracking")
        .rpc(
            "get_active_risk_zones",
            {},
        )
        .execute()
    )

    return result.data or []


def get_active_risk_zones_geojson():
    result = (
        supabase
        .schema("tracking")
        .rpc(
            "get_active_risk_zones_geojson",
            {},
        )
        .execute()
    )

    return result.data or []


def get_vessel_current_risk(mmsi):
    result = (
        supabase
        .schema("tracking")
        .rpc(
            "match_vessel_current_position",
            {
                "p_mmsi": _normalize_mmsi(mmsi),
            },
        )
        .execute()
    )

    return result.data or []


def get_tracked_vessels_in_risk_zones():
    result = (
        supabase
        .schema("tracking")
        .rpc(
            "match_tracked_vessels_current_positions",
            {},
        )
        .execute()
    )

    return result.data or []


def record_current_risk_matches():
    result = (
        supabase
        .schema("tracking")
        .rpc(
            "record_current_tracked_vessel_risk_matches",
            {},
        )
        .execute()
    )

    if not result.data:
        return {
            "inserted_count": 0,
        }

    return result.data[0]

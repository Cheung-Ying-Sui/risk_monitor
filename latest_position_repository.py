from supabase_client import supabase


LATEST_POSITION_FIELDS = (
    "vessel_id,position_id,mmsi,latitude,longitude,sog,cog,heading,"
    "destination,nav_status,observed_at,received_at,source_id"
)


def get_latest_positions():
    result = (
        supabase
        .schema("tracking")
        .table("latest_vessel_positions")
        .select(LATEST_POSITION_FIELDS)
        .order(
            "observed_at",
            desc=True,
        )
        .execute()
    )

    return result.data or []


def get_latest_position_by_mmsi(mmsi):
    if not mmsi:
        raise ValueError("mmsi is required.")

    result = (
        supabase
        .schema("tracking")
        .table("latest_vessel_positions")
        .select(LATEST_POSITION_FIELDS)
        .eq(
            "mmsi",
            str(mmsi),
        )
        .limit(1)
        .execute()
    )

    if not result.data:
        return None

    return result.data[0]


def get_high_risk_latest_positions():
    tracked_result = (
        supabase
        .schema("tracking")
        .table("tracked_vessels")
        .select("mmsi")
        .eq(
            "is_active",
            True,
        )
        .eq(
            "tracking_mode",
            "high_risk_monitoring",
        )
        .execute()
    )

    mmsi_list = [
        str(record["mmsi"])
        for record in tracked_result.data or []
        if record.get("mmsi")
    ]

    if not mmsi_list:
        return []

    result = (
        supabase
        .schema("tracking")
        .table("latest_vessel_positions")
        .select(LATEST_POSITION_FIELDS)
        .in_(
            "mmsi",
            mmsi_list,
        )
        .order(
            "observed_at",
            desc=True,
        )
        .execute()
    )

    return result.data or []

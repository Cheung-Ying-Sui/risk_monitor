from supabase_client import supabase


TRACKED_VESSEL_FIELDS = (
    "id,vessel_id,mmsi,tracking_mode,priority,is_active,created_at,updated_at"
)

VALID_TRACKING_MODES = {
    "query",
    "history_tracking",
    "high_risk_monitoring",
    "paused",
}


def _normalize_mmsi(mmsi):
    if not mmsi:
        raise ValueError("mmsi is required.")

    normalized_mmsi = str(mmsi).strip()
    if not normalized_mmsi:
        raise ValueError("mmsi is required.")

    return normalized_mmsi


def _normalize_tracking_mode(tracking_mode):
    if not tracking_mode:
        raise ValueError("tracking_mode is required.")

    normalized_tracking_mode = str(tracking_mode).strip()
    if normalized_tracking_mode not in VALID_TRACKING_MODES:
        raise ValueError(
            "tracking_mode must be one of: "
            f"{', '.join(sorted(VALID_TRACKING_MODES))}."
        )

    return normalized_tracking_mode


def _normalize_priority(priority):
    try:
        return int(priority)
    except (TypeError, ValueError):
        raise ValueError("priority must be an integer.")


def get_tracked_vessels():
    result = (
        supabase
        .schema("tracking")
        .table("tracked_vessels")
        .select(TRACKED_VESSEL_FIELDS)
        .eq(
            "is_active",
            True,
        )
        .order(
            "priority",
            desc=True,
        )
        .execute()
    )

    return result.data or []


def get_tracking_status(mmsi):
    result = (
        supabase
        .schema("tracking")
        .table("tracked_vessels")
        .select("mmsi,tracking_mode,is_active")
        .eq(
            "mmsi",
            _normalize_mmsi(mmsi),
        )
        .limit(1)
        .execute()
    )

    if not result.data:
        return None

    return result.data[0]


def add_tracking_vessel(
    mmsi,
    tracking_mode="history_tracking",
    priority=0,
):
    payload = {
        "mmsi": _normalize_mmsi(mmsi),
        "tracking_mode": _normalize_tracking_mode(tracking_mode),
        "priority": _normalize_priority(priority),
        "is_active": True,
    }

    result = (
        supabase
        .schema("tracking")
        .table("tracked_vessels")
        .insert(payload)
        .execute()
    )

    if not result.data:
        raise RuntimeError("Failed to add tracked vessel.")

    return result.data[0]


def disable_tracking_vessel(mmsi):
    result = (
        supabase
        .schema("tracking")
        .table("tracked_vessels")
        .update(
            {
                "is_active": False,
            }
        )
        .eq(
            "mmsi",
            _normalize_mmsi(mmsi),
        )
        .execute()
    )

    if not result.data:
        return None

    return result.data[0]


def update_tracking_mode(
    mmsi,
    tracking_mode,
):
    result = (
        supabase
        .schema("tracking")
        .table("tracked_vessels")
        .update(
            {
                "tracking_mode": _normalize_tracking_mode(tracking_mode),
            }
        )
        .eq(
            "mmsi",
            _normalize_mmsi(mmsi),
        )
        .execute()
    )

    if not result.data:
        return None

    return result.data[0]

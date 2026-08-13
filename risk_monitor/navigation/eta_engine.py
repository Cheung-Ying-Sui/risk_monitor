from __future__ import annotations

import math
from datetime import datetime, timezone
from statistics import median, pstdev

EARTH_RADIUS_NM = 3440.065
MIN_MOVING_SOG_KNOTS = 1.0
MAX_REASONABLE_SOG_KNOTS = 40.0
MIN_RECENT_SAMPLE_COUNT = 3
ARRIVED_DISTANCE_NM = 0.5


def _to_float(value):
    if value is None:
        return None

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(result):
        return None

    return result


def _parse_datetime(value):
    if value is None:
        return None

    if isinstance(value, datetime):
        parsed = value
    else:
        normalized = str(value).strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def parse_ais_eta(value, reference_time=None):
    if value is None:
        return None

    if isinstance(value, datetime):
        return _parse_datetime(value)

    raw_value = str(value).strip()
    if not raw_value:
        return None

    parsed = _parse_datetime(raw_value)
    if parsed:
        return parsed

    reference = reference_time or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    reference = reference.astimezone(timezone.utc)

    for date_format in ("%m-%d %H:%M", "%m/%d %H:%M"):
        try:
            naive = datetime.strptime(raw_value, date_format)
        except ValueError:
            continue

        candidate = naive.replace(
            year=reference.year,
            tzinfo=timezone.utc,
        )
        if candidate < reference:
            candidate = candidate.replace(year=reference.year + 1)
        return candidate

    return None


def calculate_great_circle_distance_nm(
    origin_lat,
    origin_lon,
    destination_lat,
    destination_lon,
):
    lat1 = _to_float(origin_lat)
    lon1 = _to_float(origin_lon)
    lat2 = _to_float(destination_lat)
    lon2 = _to_float(destination_lon)

    if None in (lat1, lon1, lat2, lon2):
        raise ValueError("origin and destination coordinates are required.")
    if not -90 <= lat1 <= 90 or not -90 <= lat2 <= 90:
        raise ValueError("latitude must be between -90 and 90.")
    if not -180 <= lon1 <= 180 or not -180 <= lon2 <= 180:
        raise ValueError("longitude must be between -180 and 180.")

    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad

    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(delta_lon / 2) ** 2
    )
    central_angle = 2 * math.atan2(
        math.sqrt(haversine),
        math.sqrt(1 - haversine),
    )
    return EARTH_RADIUS_NM * central_angle


def _valid_moving_speeds(points):
    speeds = []
    for point in points or []:
        speed = _to_float(point.get("sog"))
        if speed is None:
            continue
        if MIN_MOVING_SOG_KNOTS < speed <= MAX_REASONABLE_SOG_KNOTS:
            speeds.append(speed)
    return speeds


def _speed_summary(speeds):
    if not speeds:
        return {
            "count": 0,
            "median": None,
            "stddev": None,
            "iqr": None,
        }

    sorted_speeds = sorted(speeds)
    midpoint = len(sorted_speeds) // 2
    lower_half = sorted_speeds[:midpoint]
    upper_half = sorted_speeds[-midpoint:] if midpoint else sorted_speeds
    q25 = median(lower_half) if lower_half else sorted_speeds[0]
    q75 = median(upper_half) if upper_half else sorted_speeds[-1]

    return {
        "count": len(sorted_speeds),
        "median": median(sorted_speeds),
        "stddev": pstdev(sorted_speeds) if len(sorted_speeds) > 1 else 0.0,
        "iqr": q75 - q25,
    }


def _usable_current_sog(current_sog):
    speed = _to_float(current_sog)
    if speed is None:
        return None
    if MIN_MOVING_SOG_KNOTS < speed <= MAX_REASONABLE_SOG_KNOTS:
        return speed
    return None


def estimate_sailing_speed(
    recent_6h_positions=None,
    recent_24h_positions=None,
    historical_positions=None,
    current_sog=None,
):
    recent_6h_summary = _speed_summary(_valid_moving_speeds(recent_6h_positions))
    recent_24h_summary = _speed_summary(_valid_moving_speeds(recent_24h_positions))
    historical_summary = _speed_summary(_valid_moving_speeds(historical_positions))
    current_speed = _usable_current_sog(current_sog)

    result = {
        "estimated_speed_knots": None,
        "speed_method": "unavailable",
        "speed_sample_count": 0,
        "speed_variability": None,
        "speed_variability_method": "moving_sog_stddev",
        "warnings": [],
        "recent_6h_summary": recent_6h_summary,
        "recent_24h_summary": recent_24h_summary,
        "historical_summary": historical_summary,
    }

    if recent_6h_summary["count"] >= MIN_RECENT_SAMPLE_COUNT:
        result.update(
            {
                "estimated_speed_knots": recent_6h_summary["median"],
                "speed_method": "recent_6h_moving_sog_median",
                "speed_sample_count": recent_6h_summary["count"],
                "speed_variability": recent_6h_summary["stddev"],
            }
        )
        return result

    if recent_24h_summary["count"] >= MIN_RECENT_SAMPLE_COUNT:
        result.update(
            {
                "estimated_speed_knots": recent_24h_summary["median"],
                "speed_method": "recent_24h_moving_sog_median",
                "speed_sample_count": recent_24h_summary["count"],
                "speed_variability": recent_24h_summary["stddev"],
            }
        )
        if recent_6h_summary["count"]:
            result["warnings"].append("recent_6h_speed_sample_limited")
        return result

    if current_speed is not None:
        result.update(
            {
                "estimated_speed_knots": current_speed,
                "speed_method": "current_sog",
                "speed_sample_count": 1,
                "speed_variability": None,
            }
        )
        result["warnings"].append("speed_based_on_current_sog_only")
        return result

    if historical_summary["count"] >= MIN_RECENT_SAMPLE_COUNT:
        result.update(
            {
                "estimated_speed_knots": historical_summary["median"],
                "speed_method": "historical_moving_sog_median",
                "speed_sample_count": historical_summary["count"],
                "speed_variability": historical_summary["stddev"],
            }
        )
        result["warnings"].append("speed_based_on_historical_data")
        return result

    raw_current_speed = _to_float(current_sog)
    if raw_current_speed is not None and 0 <= raw_current_speed <= MIN_MOVING_SOG_KNOTS:
        result["warnings"].append("vessel_stopped_or_very_low_sog")
    else:
        result["warnings"].append("no_valid_sog")

    return result


def _confidence_level(destination_resolution, speed_context):
    if destination_resolution.get("resolution_status") != "resolved":
        return "low"

    method = speed_context.get("speed_method")
    sample_count = speed_context.get("speed_sample_count") or 0
    variability = speed_context.get("speed_variability")
    destination_confidence = destination_resolution.get("confidence")

    if destination_confidence != "high":
        return "low"

    if method == "recent_6h_moving_sog_median":
        if sample_count >= MIN_RECENT_SAMPLE_COUNT and (
            variability is None or variability <= 2.0
        ):
            return "high"
        return "medium"

    if method in {
        "recent_24h_moving_sog_median",
        "historical_moving_sog_median",
    }:
        if variability is not None and variability > 5.0:
            return "low"
        return "medium"

    return "low"


def _base_result(mmsi, current_position, destination_resolution, calculated_at):
    return {
        "status": "unavailable",
        "mmsi": str(mmsi) if mmsi is not None else None,
        "destination_raw": destination_resolution.get("raw_destination"),
        "destination_normalized": destination_resolution.get(
            "normalized_destination"
        ),
        "destination_latitude": destination_resolution.get("latitude"),
        "destination_longitude": destination_resolution.get("longitude"),
        "destination_unlocode": destination_resolution.get("unlocode"),
        "remaining_distance_nm": None,
        "great_circle_distance_nm": None,
        "navigable_distance_nm": None,
        "route_distance_ratio": None,
        "distance_method": "great_circle_baseline",
        "route_method": None,
        "estimated_route_geojson": None,
        "estimated_speed_knots": None,
        "speed_method": "unavailable",
        "estimated_remaining_hours": None,
        "estimated_arrival_at": None,
        "baseline_estimated_eta": None,
        "reported_ais_eta": None,
        "eta_difference_hours": None,
        "calculated_at": calculated_at.isoformat(),
        "confidence": "low",
        "warnings": [],
        "resolution_status": destination_resolution.get("resolution_status"),
        "resolution_method": destination_resolution.get("resolution_method"),
        "speed_sample_count": 0,
        "speed_variability": None,
        "speed_variability_method": "moving_sog_stddev",
    }


def estimate_eta(
    current_position,
    destination=None,
    speed_context=None,
    destination_resolution=None,
    route_result=None,
    calculated_at=None,
):
    calculated_at = calculated_at or datetime.now(timezone.utc)
    if calculated_at.tzinfo is None:
        calculated_at = calculated_at.replace(tzinfo=timezone.utc)
    calculated_at = calculated_at.astimezone(timezone.utc)

    current_position = current_position or {}
    if destination_resolution is None:
        raw_destination = (
            destination
            if destination is not None
            else current_position.get("destination")
        )
        destination_resolution = {
            "raw_destination": raw_destination,
            "normalized_destination": None,
            "latitude": None,
            "longitude": None,
            "resolution_status": "unresolved",
            "resolution_method": "destination_resolution_not_provided",
            "confidence": "low",
        }
    result = _base_result(
        current_position.get("mmsi"),
        current_position,
        destination_resolution,
        calculated_at,
    )

    if destination_resolution.get("resolution_status") == "missing":
        result["warnings"].append("destination_missing")
        return result
    if destination_resolution.get("resolution_status") != "resolved":
        result["warnings"].append("destination_unresolved")
        return result

    origin_lat = current_position.get("latitude")
    origin_lon = current_position.get("longitude")
    try:
        remaining_distance = calculate_great_circle_distance_nm(
            origin_lat,
            origin_lon,
            destination_resolution["latitude"],
            destination_resolution["longitude"],
        )
    except ValueError as exc:
        result["warnings"].append(f"invalid_current_position:{exc}")
        return result

    result["great_circle_distance_nm"] = remaining_distance
    result["remaining_distance_nm"] = remaining_distance
    result["estimated_route_geojson"] = {
        "type": "LineString",
        "coordinates": [
            [
                _to_float(origin_lon),
                _to_float(origin_lat),
            ],
            [
                _to_float(destination_resolution["longitude"]),
                _to_float(destination_resolution["latitude"]),
            ],
        ],
    }

    if route_result:
        result["route_method"] = route_result.get("route_method")
        result["estimated_route_geojson"] = route_result.get(
            "estimated_route_geojson"
        ) or result["estimated_route_geojson"]
        result["warnings"].extend(route_result.get("warnings") or [])
        result["great_circle_distance_nm"] = route_result.get(
            "great_circle_distance_nm",
            remaining_distance,
        )
        result["navigable_distance_nm"] = route_result.get("navigable_distance_nm")
        result["route_distance_ratio"] = route_result.get("route_distance_ratio")
        if (
            route_result.get("status") == "estimated"
            and route_result.get("navigable_distance_nm") is not None
        ):
            result["remaining_distance_nm"] = route_result["navigable_distance_nm"]
            result["distance_method"] = "navigable_route_baseline"

    if remaining_distance <= ARRIVED_DISTANCE_NM:
        result["status"] = "estimated"
        result["estimated_speed_knots"] = 0.0
        result["speed_method"] = "arrived_distance_threshold"
        result["estimated_remaining_hours"] = 0.0
        result["estimated_arrival_at"] = calculated_at.isoformat()
        result["baseline_estimated_eta"] = result["estimated_arrival_at"]
        result["confidence"] = "medium"
        result["warnings"].append("destination_position_matches_current_position")
        return _with_ais_eta_comparison(result, current_position, calculated_at)

    if speed_context is None:
        speed_context = estimate_sailing_speed(
            current_sog=current_position.get("sog")
        )

    result["warnings"].extend(speed_context.get("warnings", []))
    result["estimated_speed_knots"] = speed_context.get("estimated_speed_knots")
    result["speed_method"] = speed_context.get("speed_method", "unavailable")
    result["speed_sample_count"] = speed_context.get("speed_sample_count", 0)
    result["speed_variability"] = speed_context.get("speed_variability")

    speed = _to_float(result["estimated_speed_knots"])
    if speed is None or speed <= 0:
        result["warnings"].append("estimated_speed_unavailable")
        return result

    remaining_hours = result["remaining_distance_nm"] / speed
    estimated_arrival = calculated_at.timestamp() + remaining_hours * 3600
    estimated_arrival_at = datetime.fromtimestamp(
        estimated_arrival,
        tz=timezone.utc,
    )

    result["status"] = "estimated"
    result["estimated_remaining_hours"] = remaining_hours
    result["estimated_arrival_at"] = estimated_arrival_at.isoformat()
    result["baseline_estimated_eta"] = result["estimated_arrival_at"]
    result["confidence"] = _confidence_level(destination_resolution, speed_context)

    if result["speed_variability"] is not None and result["speed_variability"] > 5:
        result["warnings"].append("speed_variability_high")

    return _with_ais_eta_comparison(result, current_position, calculated_at)


def _with_ais_eta_comparison(result, current_position, calculated_at):
    ais_eta = parse_ais_eta(
        current_position.get("eta"),
        reference_time=calculated_at,
    )
    if not current_position.get("eta"):
        return result

    if not ais_eta:
        result["warnings"].append("malformed_ais_eta")
        return result

    result["reported_ais_eta"] = ais_eta.isoformat()
    baseline_eta = _parse_datetime(result.get("baseline_estimated_eta"))
    if baseline_eta:
        difference_seconds = (baseline_eta - ais_eta).total_seconds()
        result["eta_difference_hours"] = difference_seconds / 3600

    return result

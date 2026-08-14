from __future__ import annotations

import math

from risk_monitor.navigation.eta_engine import EARTH_RADIUS_NM


ROUTE_DISTANCE_DEVIATION_NM = 8.0
COURSE_DEVIATION_DEG = 45.0
MIN_CONSECUTIVE_DEVIATION_POINTS = 3


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


def _position_coordinates(position):
    position = position or {}
    latitude = _to_float(position.get("latitude", position.get("lat")))
    longitude = _to_float(position.get("longitude", position.get("lon")))
    if latitude is None or longitude is None:
        return None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    return latitude, longitude


def _route_coordinates(estimated_route_geojson):
    if not isinstance(estimated_route_geojson, dict):
        return None
    if estimated_route_geojson.get("type") != "LineString":
        return None

    coordinates = estimated_route_geojson.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return None

    route_points = []
    for coordinate in coordinates:
        if not isinstance(coordinate, (list, tuple)) or len(coordinate) < 2:
            return None
        longitude = _to_float(coordinate[0])
        latitude = _to_float(coordinate[1])
        if latitude is None or longitude is None:
            return None
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            return None
        route_points.append((latitude, longitude))

    return route_points


def calculate_bearing_deg(origin_lat, origin_lon, destination_lat, destination_lon):
    lat1 = math.radians(float(origin_lat))
    lat2 = math.radians(float(destination_lat))
    delta_lon = math.radians(float(destination_lon) - float(origin_lon))

    y = math.sin(delta_lon) * math.cos(lat2)
    x = (
        math.cos(lat1) * math.sin(lat2)
        - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon)
    )
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def calculate_bearing_difference_deg(left_bearing, right_bearing):
    left = _to_float(left_bearing)
    right = _to_float(right_bearing)
    if left is None or right is None:
        return None

    return abs((left - right + 180.0) % 360.0 - 180.0)


def _point_segment_distance_nm(point_lat, point_lon, start, end):
    start_lat, start_lon = start
    end_lat, end_lon = end
    reference_lat = math.radians(point_lat)
    point_x = 0.0
    point_y = 0.0
    start_x = (
        math.radians(start_lon - point_lon)
        * math.cos((math.radians(start_lat) + reference_lat) / 2.0)
        * EARTH_RADIUS_NM
    )
    start_y = math.radians(start_lat - point_lat) * EARTH_RADIUS_NM
    end_x = (
        math.radians(end_lon - point_lon)
        * math.cos((math.radians(end_lat) + reference_lat) / 2.0)
        * EARTH_RADIUS_NM
    )
    end_y = math.radians(end_lat - point_lat) * EARTH_RADIUS_NM

    segment_x = end_x - start_x
    segment_y = end_y - start_y
    segment_length_sq = segment_x * segment_x + segment_y * segment_y
    if segment_length_sq == 0:
        return math.hypot(start_x - point_x, start_y - point_y)

    projection = -(
        start_x * segment_x + start_y * segment_y
    ) / segment_length_sq
    projection = max(0.0, min(1.0, projection))
    nearest_x = start_x + projection * segment_x
    nearest_y = start_y + projection * segment_y
    return math.hypot(nearest_x - point_x, nearest_y - point_y)


def _nearest_route_segment(current_position, estimated_route_geojson):
    position_coordinates = _position_coordinates(current_position)
    route_points = _route_coordinates(estimated_route_geojson)
    if position_coordinates is None or route_points is None:
        return None

    point_lat, point_lon = position_coordinates
    nearest_segment = None
    nearest_distance = None
    for index, (start, end) in enumerate(zip(route_points, route_points[1:])):
        distance = _point_segment_distance_nm(point_lat, point_lon, start, end)
        if nearest_distance is None or distance < nearest_distance:
            nearest_distance = distance
            nearest_segment = {
                "index": index,
                "start": start,
                "end": end,
                "distance_nm": distance,
            }

    return nearest_segment


def calculate_distance_to_route(current_position, estimated_route_geojson):
    nearest_segment = _nearest_route_segment(
        current_position,
        estimated_route_geojson,
    )
    if nearest_segment is None:
        return None

    return nearest_segment["distance_nm"]


def calculate_route_bearing_near_position(current_position, estimated_route_geojson):
    nearest_segment = _nearest_route_segment(
        current_position,
        estimated_route_geojson,
    )
    if nearest_segment is None:
        return None

    start_lat, start_lon = nearest_segment["start"]
    end_lat, end_lon = nearest_segment["end"]
    return calculate_bearing_deg(start_lat, start_lon, end_lat, end_lon)


def _single_point_deviation(
    position,
    current_cog,
    estimated_route_geojson,
    distance_threshold_nm,
    course_threshold_deg,
):
    distance_to_route = calculate_distance_to_route(
        position,
        estimated_route_geojson,
    )
    expected_bearing = calculate_route_bearing_near_position(
        position,
        estimated_route_geojson,
    )
    course_difference = calculate_bearing_difference_deg(
        current_cog,
        expected_bearing,
    )

    distance_deviation = (
        distance_to_route is not None
        and distance_to_route > distance_threshold_nm
    )
    course_deviation = (
        course_difference is not None
        and course_difference > course_threshold_deg
    )

    return {
        "distance_to_route_nm": distance_to_route,
        "expected_route_bearing_deg": expected_bearing,
        "current_cog_deg": _to_float(current_cog),
        "course_difference_deg": course_difference,
        "distance_deviation": distance_deviation,
        "course_deviation": course_deviation,
        "is_deviating": bool(distance_deviation or course_deviation),
    }


def _consecutive_deviation_count(
    current_position,
    current_cog,
    estimated_route_geojson,
    recent_positions,
    distance_threshold_nm,
    course_threshold_deg,
):
    positions = list(recent_positions or [])
    if current_position:
        latest_key = None
        last_key = None
        if isinstance(current_position, dict):
            latest_key = (
                current_position.get("observed_at"),
                current_position.get("latitude", current_position.get("lat")),
                current_position.get("longitude", current_position.get("lon")),
            )
        if positions and isinstance(positions[-1], dict):
            last_key = (
                positions[-1].get("observed_at"),
                positions[-1].get("latitude", positions[-1].get("lat")),
                positions[-1].get("longitude", positions[-1].get("lon")),
            )
        if not positions or not latest_key or latest_key != last_key:
            positions.append(current_position)

    count = 0
    for position in reversed(positions):
        point_cog = (
            position.get("cog", current_cog)
            if isinstance(position, dict)
            else None
        )
        point_result = _single_point_deviation(
            position,
            point_cog,
            estimated_route_geojson,
            distance_threshold_nm,
            course_threshold_deg,
        )
        if not point_result["is_deviating"]:
            break
        count += 1

    return count


def evaluate_route_deviation(
    current_position,
    current_cog,
    estimated_route_geojson,
    route_created_at=None,
    route_origin=None,
    recent_positions=None,
    distance_threshold_nm=ROUTE_DISTANCE_DEVIATION_NM,
    course_threshold_deg=COURSE_DEVIATION_DEG,
    min_consecutive_deviation_points=MIN_CONSECUTIVE_DEVIATION_POINTS,
):
    reasons = []
    if _position_coordinates(current_position) is None:
        reasons.append("missing_current_position")
    if _route_coordinates(estimated_route_geojson) is None:
        reasons.append("missing_or_malformed_route")

    if reasons:
        return {
            "status": "unavailable",
            "distance_to_route_nm": None,
            "expected_route_bearing_deg": None,
            "current_cog_deg": _to_float(current_cog),
            "course_difference_deg": None,
            "distance_deviation": False,
            "course_deviation": False,
            "consecutive_deviation_points": 0,
            "required_consecutive_deviation_points": min_consecutive_deviation_points,
            "recalculation_recommended": False,
            "reasons": reasons,
            "route_created_at": route_created_at,
            "route_origin": route_origin,
        }

    point_result = _single_point_deviation(
        current_position,
        current_cog,
        estimated_route_geojson,
        distance_threshold_nm,
        course_threshold_deg,
    )
    if point_result["current_cog_deg"] is None:
        reasons.append("missing_cog")
    if point_result["distance_deviation"]:
        reasons.append("distance_threshold_exceeded")
    if point_result["course_deviation"]:
        reasons.append("course_threshold_exceeded")

    consecutive_count = 0
    if point_result["is_deviating"]:
        consecutive_count = _consecutive_deviation_count(
            current_position,
            current_cog,
            estimated_route_geojson,
            recent_positions,
            distance_threshold_nm,
            course_threshold_deg,
        )

    recalculation_recommended = (
        point_result["is_deviating"]
        and consecutive_count >= int(min_consecutive_deviation_points)
    )
    if recalculation_recommended:
        reasons.append("consecutive_deviation_threshold_met")

    return {
        "status": "deviating" if point_result["is_deviating"] else "on_route",
        "distance_to_route_nm": point_result["distance_to_route_nm"],
        "expected_route_bearing_deg": point_result["expected_route_bearing_deg"],
        "current_cog_deg": point_result["current_cog_deg"],
        "course_difference_deg": point_result["course_difference_deg"],
        "distance_deviation": point_result["distance_deviation"],
        "course_deviation": point_result["course_deviation"],
        "consecutive_deviation_points": consecutive_count,
        "required_consecutive_deviation_points": min_consecutive_deviation_points,
        "recalculation_recommended": recalculation_recommended,
        "reasons": reasons,
        "route_created_at": route_created_at,
        "route_origin": route_origin,
    }

from __future__ import annotations

from statistics import mean, median

from risk_monitor.navigation.eta_engine import calculate_great_circle_distance_nm
from risk_monitor.navigation.route_monitor import (
    ROUTE_DISTANCE_DEVIATION_NM,
    calculate_distance_to_route,
)


MIN_OBSERVATIONS_FOR_TRACK_EVALUATION = 2


def _to_float(value):
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result


def _route_coordinates(route_geojson):
    if not isinstance(route_geojson, dict):
        return None
    if route_geojson.get("type") != "LineString":
        return None

    coordinates = route_geojson.get("coordinates")
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
        route_points.append(
            {
                "latitude": latitude,
                "longitude": longitude,
            }
        )
    return route_points


def _route_distance_nm(route_points):
    total = 0.0
    for start, end in zip(route_points, route_points[1:]):
        total += calculate_great_circle_distance_nm(
            start["latitude"],
            start["longitude"],
            end["latitude"],
            end["longitude"],
        )
    return total


def _point_segment_projection_ratio(point, start, end):
    point_lat = point["latitude"]
    point_lon = point["longitude"]
    start_lat = start["latitude"]
    start_lon = start["longitude"]
    end_lat = end["latitude"]
    end_lon = end["longitude"]

    segment_lat = end_lat - start_lat
    segment_lon = end_lon - start_lon
    segment_length_sq = segment_lat * segment_lat + segment_lon * segment_lon
    if segment_length_sq == 0:
        return 0.0

    projection = (
        (point_lat - start_lat) * segment_lat
        + (point_lon - start_lon) * segment_lon
    ) / segment_length_sq
    return max(0.0, min(1.0, projection))


def _route_progress_ratio(predicted_route_geojson, point):
    route_points = _route_coordinates(predicted_route_geojson)
    if not route_points or not point:
        return None

    point_lat = _to_float(point.get("latitude"))
    point_lon = _to_float(point.get("longitude"))
    if point_lat is None or point_lon is None:
        return None
    point = {
        "latitude": point_lat,
        "longitude": point_lon,
    }

    total_distance = _route_distance_nm(route_points)
    if total_distance <= 0:
        return None

    best_segment_index = None
    best_distance = None
    for index, (start, end) in enumerate(zip(route_points, route_points[1:])):
        segment_route = {
            "type": "LineString",
            "coordinates": [
                [
                    start["longitude"],
                    start["latitude"],
                ],
                [
                    end["longitude"],
                    end["latitude"],
                ],
            ],
        }
        distance = calculate_distance_to_route(point, segment_route)
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_segment_index = index

    progress_distance = 0.0
    for start, end in zip(route_points, route_points[1:best_segment_index + 1]):
        progress_distance += calculate_great_circle_distance_nm(
            start["latitude"],
            start["longitude"],
            end["latitude"],
            end["longitude"],
        )

    start = route_points[best_segment_index]
    end = route_points[best_segment_index + 1]
    segment_ratio = _point_segment_projection_ratio(point, start, end)
    segment_distance = calculate_great_circle_distance_nm(
        start["latitude"],
        start["longitude"],
        end["latitude"],
        end["longitude"],
    )
    progress_distance += segment_ratio * segment_distance
    return max(0.0, min(1.0, progress_distance / total_distance))


def _percentile(values, percentile):
    if not values:
        return None
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * percentile
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    weight = rank - lower_index
    return (
        sorted_values[lower_index] * (1.0 - weight)
        + sorted_values[upper_index] * weight
    )


def _point_error(predicted_route_geojson, point):
    distance = calculate_distance_to_route(point, predicted_route_geojson)
    return {
        "position_id": point.get("position_id") or point.get("id"),
        "observed_at": point.get("observed_at"),
        "latitude": point.get("latitude"),
        "longitude": point.get("longitude"),
        "cog": point.get("cog"),
        "sog": point.get("sog"),
        "distance_to_predicted_route_nm": distance,
        "route_progress_ratio": _route_progress_ratio(
            predicted_route_geojson,
            point,
        ),
    }


def evaluate_actual_track_against_route(
    predicted_route_geojson,
    actual_track_points,
    adherence_threshold_nm=ROUTE_DISTANCE_DEVIATION_NM,
):
    if _route_coordinates(predicted_route_geojson) is None:
        return {
            "status": "unavailable",
            "observation_count": 0,
            "point_errors": [],
            "mean_deviation_nm": None,
            "median_deviation_nm": None,
            "max_deviation_nm": None,
            "p90_deviation_nm": None,
            "route_adherence_ratio": None,
            "route_progress_ratio": None,
            "adherence_threshold_nm": adherence_threshold_nm,
            "reasons": ["missing_or_malformed_route"],
        }

    points = list(actual_track_points or [])
    if not points:
        return {
            "status": "awaiting_data",
            "observation_count": 0,
            "point_errors": [],
            "mean_deviation_nm": None,
            "median_deviation_nm": None,
            "max_deviation_nm": None,
            "p90_deviation_nm": None,
            "route_adherence_ratio": None,
            "route_progress_ratio": None,
            "adherence_threshold_nm": adherence_threshold_nm,
            "reasons": ["no_actual_ais_after_prediction"],
        }

    point_errors = [_point_error(predicted_route_geojson, point) for point in points]
    distances = [
        error["distance_to_predicted_route_nm"]
        for error in point_errors
        if error["distance_to_predicted_route_nm"] is not None
    ]
    if not distances:
        return {
            "status": "unavailable",
            "observation_count": len(points),
            "point_errors": point_errors,
            "mean_deviation_nm": None,
            "median_deviation_nm": None,
            "max_deviation_nm": None,
            "p90_deviation_nm": None,
            "route_adherence_ratio": None,
            "route_progress_ratio": None,
            "adherence_threshold_nm": adherence_threshold_nm,
            "reasons": ["actual_track_points_invalid"],
        }

    adherence_count = sum(
        1
        for distance in distances
        if distance <= adherence_threshold_nm
    )
    route_progress = point_errors[-1].get("route_progress_ratio")
    status = "following_prediction"
    reasons = []
    if len(points) < MIN_OBSERVATIONS_FOR_TRACK_EVALUATION:
        status = "insufficient_data"
        reasons.append("insufficient_actual_ais_points")
    elif adherence_count < len(distances):
        status = "deviating"
        reasons.append("one_or_more_points_exceed_adherence_threshold")

    return {
        "status": status,
        "observation_count": len(points),
        "point_errors": point_errors,
        "mean_deviation_nm": mean(distances),
        "median_deviation_nm": median(distances),
        "max_deviation_nm": max(distances),
        "p90_deviation_nm": _percentile(distances, 0.9),
        "route_adherence_ratio": adherence_count / len(distances),
        "route_progress_ratio": route_progress,
        "adherence_threshold_nm": adherence_threshold_nm,
        "reasons": reasons,
    }

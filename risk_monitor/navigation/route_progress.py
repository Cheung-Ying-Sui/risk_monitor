from __future__ import annotations

import math
from typing import Any

from risk_monitor.navigation.eta_engine import (
    EARTH_RADIUS_NM,
    calculate_great_circle_distance_nm,
)


class RouteProjectionAmbiguous(ValueError):
    """Multiple separated route legs fit this AIS point; no reliable progress."""


def _to_float(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("route coordinates must be numeric.") from exc
    if not math.isfinite(result):
        raise ValueError("route coordinates must be finite.")
    return result


def _normalize_longitude(longitude: float) -> float:
    return (longitude + 180.0) % 360.0 - 180.0


def _longitude_delta(start: float, end: float) -> float:
    return (end - start + 180.0) % 360.0 - 180.0


def _route_coordinates(route_geojson: dict[str, Any]) -> list[tuple[float, float]]:
    if not isinstance(route_geojson, dict) or route_geojson.get("type") != "LineString":
        raise ValueError("route_geojson must be a GeoJSON LineString.")

    coordinates = route_geojson.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise ValueError("route_geojson must contain at least two coordinates.")

    route = []
    for coordinate in coordinates:
        if not isinstance(coordinate, (list, tuple)) or len(coordinate) < 2:
            raise ValueError("route coordinate must contain longitude and latitude.")
        longitude = _to_float(coordinate[0])
        latitude = _to_float(coordinate[1])
        if not -180.0 <= longitude <= 180.0:
            raise ValueError("route longitude must be between -180 and 180.")
        if not -90.0 <= latitude <= 90.0:
            raise ValueError("route latitude must be between -90 and 90.")
        route.append((longitude, latitude))
    return route


def _position_coordinates(position: dict[str, Any]) -> tuple[float, float]:
    if not isinstance(position, dict):
        raise ValueError("current_position is required.")
    longitude = _to_float(position.get("longitude", position.get("lon")))
    latitude = _to_float(position.get("latitude", position.get("lat")))
    if not -180.0 <= longitude <= 180.0:
        raise ValueError("position longitude must be between -180 and 180.")
    if not -90.0 <= latitude <= 90.0:
        raise ValueError("position latitude must be between -90 and 90.")
    return longitude, latitude


def _segment_projection(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> tuple[float, tuple[float, float]]:
    point_lon, point_lat = point
    start_lon, start_lat = start
    end_lon, end_lat = end

    segment_lon_delta = _longitude_delta(start_lon, end_lon)
    point_lon_delta = _longitude_delta(start_lon, point_lon)
    reference_lat = math.radians((start_lat + end_lat + point_lat) / 3.0)
    longitude_scale = max(abs(math.cos(reference_lat)), 1e-9)

    segment_x = math.radians(segment_lon_delta) * longitude_scale * EARTH_RADIUS_NM
    segment_y = math.radians(end_lat - start_lat) * EARTH_RADIUS_NM
    point_x = math.radians(point_lon_delta) * longitude_scale * EARTH_RADIUS_NM
    point_y = math.radians(point_lat - start_lat) * EARTH_RADIUS_NM
    segment_length_squared = segment_x * segment_x + segment_y * segment_y
    if segment_length_squared == 0:
        return 0.0, start

    fraction = (point_x * segment_x + point_y * segment_y) / segment_length_squared
    fraction = max(0.0, min(1.0, fraction))
    projected_lon = _normalize_longitude(start_lon + fraction * segment_lon_delta)
    projected_lat = start_lat + fraction * (end_lat - start_lat)
    return fraction, (projected_lon, projected_lat)


def calculate_route_progress(
    current_position: dict[str, Any],
    route_geojson: dict[str, Any],
    *,
    reject_ambiguous: bool = False,
) -> dict[str, Any]:
    """Project a vessel onto a persisted route and return remaining-route metrics."""

    route = _route_coordinates(route_geojson)
    point = _position_coordinates(current_position)
    segment_distances = [
        calculate_great_circle_distance_nm(start[1], start[0], end[1], end[0])
        for start, end in zip(route, route[1:])
    ]
    total_distance_nm = sum(segment_distances)
    if total_distance_nm <= 0:
        raise ValueError("route_geojson must have a positive length.")

    best: dict[str, Any] | None = None
    candidates = []
    distance_before_segment = 0.0
    for index, (start, end, segment_distance_nm) in enumerate(
        zip(route, route[1:], segment_distances)
    ):
        segment_fraction, projected = _segment_projection(point, start, end)
        cross_track_error_nm = calculate_great_circle_distance_nm(
            point[1], point[0], projected[1], projected[0]
        )
        distance_along_route_nm = (
            distance_before_segment + segment_distance_nm * segment_fraction
        )
        candidate = {
            "segment_index": index,
            "segment_fraction": segment_fraction,
            "projected": projected,
            "cross_track_error_nm": cross_track_error_nm,
            "distance_along_route_nm": distance_along_route_nm,
        }
        candidates.append(candidate)
        if best is None or cross_track_error_nm < best["cross_track_error_nm"] - 1e-9:
            best = candidate
        elif (
            abs(cross_track_error_nm - best["cross_track_error_nm"]) <= 1e-9
            and distance_along_route_nm > best["distance_along_route_nm"]
        ):
            best = candidate
        distance_before_segment += segment_distance_nm

    assert best is not None
    if reject_ambiguous and any(
        c['cross_track_error_nm'] <= best['cross_track_error_nm'] + 1.0
        and abs(c['distance_along_route_nm'] - best['distance_along_route_nm']) > 5.0
        for c in candidates
    ):
        raise RouteProjectionAmbiguous('route_projection_ambiguous')
    progress = max(
        0.0,
        min(1.0, best["distance_along_route_nm"] / total_distance_nm),
    )
    remaining_distance_nm = max(
        0.0,
        total_distance_nm - best["distance_along_route_nm"],
    )
    projected_lon, projected_lat = best["projected"]
    remaining_coordinates = [
        [projected_lon, projected_lat],
        *[
            [longitude, latitude]
            for longitude, latitude in route[best["segment_index"] + 1 :]
        ],
    ]
    if len(remaining_coordinates) == 1:
        remaining_coordinates.append(list(remaining_coordinates[0]))

    return {
        "route_progress": progress,
        "cross_track_error_nm": best["cross_track_error_nm"],
        "cross_track_error_m": best["cross_track_error_nm"] * 1852.0,
        "remaining_distance_nm": remaining_distance_nm,
        "total_route_distance_nm": total_distance_nm,
        "distance_along_route_nm": best["distance_along_route_nm"],
        "projected_position": {
            "longitude": projected_lon,
            "latitude": projected_lat,
        },
        "remaining_route_geojson": {
            "type": "LineString",
            "coordinates": remaining_coordinates,
        },
        "matched_segment_index": best["segment_index"],
        "matched_segment_fraction": best["segment_fraction"],
    }

from __future__ import annotations

import heapq
import json
import math
from functools import lru_cache
from pathlib import Path

from shapely.geometry import LineString, Point, shape
from shapely.ops import unary_union
from shapely.prepared import prep

from risk_monitor.navigation.eta_engine import calculate_great_circle_distance_nm


DEFAULT_LAND_MASK_PATH = Path(__file__).resolve().parents[2] / "static" / "land_mask.json"
ENDPOINT_TOLERANCE_DEGREES = 0.75
WAYPOINT_MARGIN_DEGREES = 1.0
MAX_INTERSECTING_LAND_FEATURES = 20
REGIONAL_CORRIDORS = [
    {
        "name": "english_channel_to_western_mediterranean",
        "bbox": {
            "min_lat": 30.0,
            "max_lat": 55.0,
            "min_lon": -12.0,
            "max_lon": 2.0,
        },
        "waypoints": [
            {
                "lat": 50.0,
                "lon": -1.5,
            },
            {
                "lat": 49.8,
                "lon": -5.0,
            },
            {
                "lat": 47.0,
                "lon": -9.0,
            },
            {
                "lat": 43.0,
                "lon": -11.5,
            },
            {
                "lat": 38.0,
                "lon": -11.5,
            },
            {
                "lat": 35.8,
                "lon": -6.5,
            },
        ],
    },
    {
        "name": "eastern_atlantic_to_english_channel",
        "bbox": {
            "min_lat": -5.0,
            "max_lat": 55.0,
            "min_lon": -25.0,
            "max_lon": 2.0,
        },
        "waypoints": [
            {
                "lat": 15.0,
                "lon": -20.0,
            },
            {
                "lat": 35.0,
                "lon": -15.0,
            },
            {
                "lat": 47.0,
                "lon": -9.0,
            },
            {
                "lat": 49.8,
                "lon": -5.0,
            },
            {
                "lat": 50.0,
                "lon": -1.5,
            },
        ],
    },
    {
        "name": "south_china_to_yellow_sea",
        "bbox": {
            "min_lat": 18.0,
            "max_lat": 38.0,
            "min_lon": 116.0,
            "max_lon": 126.0,
        },
        "waypoints": [
            {
                "lat": 22.0,
                "lon": 120.5,
            },
            {
                "lat": 24.0,
                "lon": 124.5,
            },
            {
                "lat": 30.0,
                "lon": 125.0,
            },
            {
                "lat": 35.0,
                "lon": 124.0,
            },
        ],
    },
    {
        "name": "east_china_to_lianyungang",
        "bbox": {
            "min_lat": 24.0,
            "max_lat": 36.0,
            "min_lon": 118.0,
            "max_lon": 126.0,
        },
        "waypoints": [
            {
                "lat": 31.0,
                "lon": 124.5,
            },
            {
                "lat": 34.8,
                "lon": 121.5,
            },
        ],
    },
]


def _to_float(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _validate_point(lat, lon):
    latitude = _to_float(lat)
    longitude = _to_float(lon)
    if latitude is None or longitude is None:
        raise ValueError("route coordinates are required.")
    if not -90 <= latitude <= 90:
        raise ValueError("latitude must be between -90 and 90.")
    if not -180 <= longitude <= 180:
        raise ValueError("longitude must be between -180 and 180.")
    return latitude, longitude


@lru_cache(maxsize=4)
def load_land_geometries(path=DEFAULT_LAND_MASK_PATH):
    land_path = Path(path)
    data = json.loads(land_path.read_text(encoding="utf-8"))
    features = data.get("features") or []
    geometries = []
    for feature in features:
        geometry = feature.get("geometry")
        if geometry:
            geometries.append(shape(geometry))

    land_union = unary_union(geometries)
    return {
        "features": geometries,
        "union": land_union,
        "prepared": prep(land_union),
    }


def _line(origin, destination):
    return LineString(
        [
            (origin["lon"], origin["lat"]),
            (destination["lon"], destination["lat"]),
        ]
    )


def _is_endpoint_intersection_only(line, land_union, origin, destination):
    intersection = line.intersection(land_union)
    if intersection.is_empty:
        return True

    endpoint_area = (
        Point(origin["lon"], origin["lat"]).buffer(ENDPOINT_TOLERANCE_DEGREES)
        .union(
            Point(destination["lon"], destination["lat"]).buffer(
                ENDPOINT_TOLERANCE_DEGREES
            )
        )
    )
    return intersection.difference(endpoint_area).is_empty


def _edge_is_navigable(origin, destination, land_data):
    line = _line(origin, destination)
    if not land_data["prepared"].intersects(line):
        return True
    return _is_endpoint_intersection_only(
        line,
        land_data["union"],
        origin,
        destination,
    )


def _route_distance_nm(points):
    total = 0.0
    for start, end in zip(points, points[1:]):
        total += calculate_great_circle_distance_nm(
            start["lat"],
            start["lon"],
            end["lat"],
            end["lon"],
        )
    return total


def _route_geojson(points):
    return {
        "type": "LineString",
        "coordinates": [
            [
                point["lon"],
                point["lat"],
            ]
            for point in points
        ],
    }


def _intersecting_land_features(direct_line, land_features):
    intersections = [
        feature
        for feature in land_features
        if feature.intersects(direct_line)
    ]
    return sorted(
        intersections,
        key=lambda geometry: geometry.area,
        reverse=True,
    )[:MAX_INTERSECTING_LAND_FEATURES]


def _candidate_waypoints(origin, destination, land_features):
    direct_line = _line(origin, destination)
    min_lon = min(origin["lon"], destination["lon"])
    max_lon = max(origin["lon"], destination["lon"])
    min_lat = min(origin["lat"], destination["lat"])
    max_lat = max(origin["lat"], destination["lat"])
    points = []
    seen = set()

    for feature in _intersecting_land_features(direct_line, land_features):
        bounds = feature.bounds
        west = max(-180.0, bounds[0] - WAYPOINT_MARGIN_DEGREES)
        south = max(-85.0, bounds[1] - WAYPOINT_MARGIN_DEGREES)
        east = min(180.0, bounds[2] + WAYPOINT_MARGIN_DEGREES)
        north = min(85.0, bounds[3] + WAYPOINT_MARGIN_DEGREES)

        expanded_overlaps_route_bbox = not (
            east < min_lon
            or west > max_lon
            or north < min_lat
            or south > max_lat
        )
        if not expanded_overlaps_route_bbox:
            continue

        for lon, lat in (
            (west, south),
            (west, north),
            (east, south),
            (east, north),
            ((west + east) / 2, south),
            ((west + east) / 2, north),
            (west, (south + north) / 2),
            (east, (south + north) / 2),
        ):
            key = (round(lon, 4), round(lat, 4))
            if key in seen:
                continue
            seen.add(key)
            points.append(
                {
                    "lat": lat,
                    "lon": lon,
                }
            )

    return points


def _shortest_visible_route(nodes, land_data):
    graph = {
        index: []
        for index in range(len(nodes))
    }
    for left_index, left in enumerate(nodes):
        for right_index in range(left_index + 1, len(nodes)):
            right = nodes[right_index]
            if not _edge_is_navigable(left, right, land_data):
                continue
            distance = calculate_great_circle_distance_nm(
                left["lat"],
                left["lon"],
                right["lat"],
                right["lon"],
            )
            graph[left_index].append((right_index, distance))
            graph[right_index].append((left_index, distance))

    queue = [(0.0, 0, [0])]
    best = {
        0: 0.0,
    }
    destination_index = 1

    while queue:
        distance, node_index, path = heapq.heappop(queue)
        if node_index == destination_index:
            return [
                nodes[index]
                for index in path
            ]
        if distance > best.get(node_index, float("inf")):
            continue
        for next_index, edge_distance in graph[node_index]:
            next_distance = distance + edge_distance
            if next_distance >= best.get(next_index, float("inf")):
                continue
            best[next_index] = next_distance
            heapq.heappush(
                queue,
                (
                    next_distance,
                    next_index,
                    [*path, next_index],
                ),
            )

    return None


def _bbox_contains_route(origin, destination, bbox):
    route_min_lat = min(origin["lat"], destination["lat"])
    route_max_lat = max(origin["lat"], destination["lat"])
    route_min_lon = min(origin["lon"], destination["lon"])
    route_max_lon = max(origin["lon"], destination["lon"])

    return not (
        route_max_lat < bbox["min_lat"]
        or route_min_lat > bbox["max_lat"]
        or route_max_lon < bbox["min_lon"]
        or route_min_lon > bbox["max_lon"]
    )


def _verified_corridor_route(origin, destination, land_data):
    best_route = None
    best_distance = None
    best_name = None

    for corridor in REGIONAL_CORRIDORS:
        if not _bbox_contains_route(
            origin,
            destination,
            corridor["bbox"],
        ):
            continue

        route_points = [
            origin,
            *corridor["waypoints"],
            destination,
        ]
        if not all(
            _edge_is_navigable(start, end, land_data)
            for start, end in zip(route_points, route_points[1:])
        ):
            continue

        distance = _route_distance_nm(route_points)
        if best_distance is None or distance < best_distance:
            best_route = route_points
            best_distance = distance
            best_name = corridor["name"]

    if not best_route:
        return None

    return {
        "route_points": best_route,
        "route_distance_nm": best_distance,
        "corridor_name": best_name,
    }


def estimate_navigable_route(
    origin_lat,
    origin_lon,
    destination_lat,
    destination_lon,
    land_mask_path=DEFAULT_LAND_MASK_PATH,
):
    origin_lat, origin_lon = _validate_point(origin_lat, origin_lon)
    destination_lat, destination_lon = _validate_point(destination_lat, destination_lon)
    origin = {
        "lat": origin_lat,
        "lon": origin_lon,
    }
    destination = {
        "lat": destination_lat,
        "lon": destination_lon,
    }
    great_circle_distance = calculate_great_circle_distance_nm(
        origin_lat,
        origin_lon,
        destination_lat,
        destination_lon,
    )

    land_data = load_land_geometries(Path(land_mask_path))
    if _edge_is_navigable(origin, destination, land_data):
        route_points = [
            origin,
            destination,
        ]
        return {
            "status": "estimated",
            "route_method": "direct_sea_baseline",
            "distance_method": "navigable_route_baseline",
            "great_circle_distance_nm": great_circle_distance,
            "navigable_distance_nm": great_circle_distance,
            "route_distance_ratio": 1.0,
            "estimated_route_geojson": _route_geojson(route_points),
            "warnings": [],
        }

    waypoints = _candidate_waypoints(
        origin,
        destination,
        land_data["features"],
    )
    route_points = _shortest_visible_route(
        [
            origin,
            destination,
            *waypoints,
        ],
        land_data,
    )
    if not route_points:
        corridor_route = _verified_corridor_route(
            origin,
            destination,
            land_data,
        )
        if corridor_route:
            route_points = corridor_route["route_points"]
            route_distance = corridor_route["route_distance_nm"]
            return {
                "status": "estimated",
                "route_method": "land_avoidance_baseline",
                "distance_method": "navigable_route_baseline",
                "great_circle_distance_nm": great_circle_distance,
                "navigable_distance_nm": route_distance,
                "route_distance_ratio": (
                    route_distance / great_circle_distance
                    if great_circle_distance
                    else 1.0
                ),
                "estimated_route_geojson": _route_geojson(route_points),
                "warnings": [
                    f"regional_corridor:{corridor_route['corridor_name']}",
                ],
            }

        return {
            "status": "unavailable",
            "route_method": "land_avoidance_baseline",
            "distance_method": "great_circle_baseline",
            "great_circle_distance_nm": great_circle_distance,
            "navigable_distance_nm": None,
            "route_distance_ratio": None,
            "estimated_route_geojson": _route_geojson([origin, destination]),
            "warnings": [
                "navigable_route_unavailable",
            ],
        }

    route_distance = _route_distance_nm(route_points)
    return {
        "status": "estimated",
        "route_method": "land_avoidance_baseline",
        "distance_method": "navigable_route_baseline",
        "great_circle_distance_nm": great_circle_distance,
        "navigable_distance_nm": route_distance,
        "route_distance_ratio": (
            route_distance / great_circle_distance
            if great_circle_distance
            else 1.0
        ),
        "estimated_route_geojson": _route_geojson(route_points),
        "warnings": [],
    }

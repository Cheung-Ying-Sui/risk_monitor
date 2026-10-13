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
ROUTE_POINT_SPACING_NM = 20.0
MAX_INTERPOLATED_SEGMENTS = 500
COURSE_WAYPOINT_MIN_ROUTE_NM = 12.0
COURSE_WAYPOINT_MIN_DISTANCE_NM = 3.0
COURSE_WAYPOINT_MAX_DISTANCE_NM = 40.0
COURSE_WAYPOINT_DISTANCE_RATIO = 0.08
COURSE_WAYPOINT_MAX_HEADING_DIFFERENCE_DEG = 65.0
COURSE_WAYPOINT_MAX_DETOUR_RATIO = 1.12
MARITIME_PASSAGES = [
    {
        "name": "suez_canal",
        "width_degrees": 0.18,
        "coordinates": [
            (32.56, 29.88),
            (32.45, 30.45),
            (32.34, 31.02),
            (32.31, 31.28),
        ],
    },
    {
        "name": "malacca_strait",
        "width_degrees": 0.45,
        "coordinates": [
            (95.20, 5.95),
            (97.00, 5.35),
            (99.00, 3.85),
            (101.00, 2.65),
            (103.35, 1.25),
        ],
    },
    {
        "name": "english_channel",
        "width_degrees": 0.35,
        "coordinates": [
            (-5.20, 49.55),
            (-2.50, 49.75),
            (-1.20, 50.20),
            (1.45, 51.10),
        ],
    },
]

# Strategic sea points form a sparse, deterministic fallback graph. They do not
# claim navigational precision; every graph edge is still checked against the
# project land mask (except the controlled canal/strait centerlines above).
GLOBAL_MARITIME_WAYPOINTS = [
    # North Sea, English Channel, Atlantic and Gibraltar.
    {"lat": 52.0, "lon": 3.5},
    {"lat": 51.1, "lon": 1.45},
    {"lat": 50.2, "lon": -1.2},
    {"lat": 49.55, "lon": -5.2},
    {"lat": 47.0, "lon": -9.0},
    {"lat": 43.0, "lon": -10.5},
    {"lat": 38.0, "lon": -11.5},
    {"lat": 36.0, "lon": -8.0},
    {"lat": 35.95, "lon": -5.6},
    # Mediterranean and Suez.
    {"lat": 37.0, "lon": 3.0},
    {"lat": 38.0, "lon": 0.0},
    {"lat": 37.0, "lon": -1.0},
    {"lat": 36.0, "lon": -3.0},
    {"lat": 36.2, "lon": 11.5},
    {"lat": 37.0, "lon": 12.0},
    {"lat": 38.0, "lon": 10.0},
    {"lat": 38.0, "lon": 8.0},
    {"lat": 38.0, "lon": 6.0},
    {"lat": 38.0, "lon": 4.0},
    {"lat": 38.0, "lon": 2.0},
    {"lat": 34.2, "lon": 19.0},
    {"lat": 33.4, "lon": 26.0},
    {"lat": 32.2, "lon": 30.0},
    {"lat": 31.28, "lon": 32.31},
    {"lat": 30.45, "lon": 32.45},
    {"lat": 29.88, "lon": 32.56},
    # Red Sea, Gulf of Aden, Arabian Sea and Persian Gulf entrance.
    {"lat": 28.5, "lon": 33.0},
    {"lat": 27.2, "lon": 34.0},
    {"lat": 21.0, "lon": 38.5},
    {"lat": 15.0, "lon": 41.8},
    {"lat": 12.5, "lon": 43.4},
    {"lat": 12.0, "lon": 48.0},
    {"lat": 14.0, "lon": 54.0},
    {"lat": 20.0, "lon": 59.0},
    {"lat": 24.5, "lon": 58.5},
    {"lat": 25.4, "lon": 56.5},
    # West and south Africa, then western Indian Ocean.
    {"lat": 10.0, "lon": -18.0},
    {"lat": 0.0, "lon": -12.0},
    {"lat": -12.0, "lon": -5.0},
    {"lat": -23.0, "lon": 5.0},
    {"lat": -35.0, "lon": 17.0},
    {"lat": -36.0, "lon": 22.0},
    {"lat": -32.0, "lon": 31.0},
    {"lat": -22.0, "lon": 40.0},
    {"lat": -10.0, "lon": 48.0},
    {"lat": -10.0, "lon": 55.0},
    {"lat": 0.0, "lon": 52.0},
    {"lat": 0.0, "lon": 60.0},
    {"lat": 8.0, "lon": 55.0},
    {"lat": 10.0, "lon": 62.0},
    {"lat": 20.0, "lon": 62.0},
    # Indian Ocean, Sri Lanka, Malacca and South China Sea.
    {"lat": 5.0, "lon": 70.0},
    {"lat": 5.8, "lon": 79.0},
    {"lat": 6.3, "lon": 88.0},
    {"lat": 5.95, "lon": 95.2},
    {"lat": 5.35, "lon": 97.0},
    {"lat": 3.85, "lon": 99.0},
    {"lat": 2.65, "lon": 101.0},
    {"lat": 1.25, "lon": 103.35},
    {"lat": 3.0, "lon": 105.5},
    {"lat": 10.0, "lon": 110.0},
    {"lat": 17.0, "lon": 114.0},
    {"lat": 22.0, "lon": 118.0},
    {"lat": 24.0, "lon": 124.5},
    {"lat": 30.0, "lon": 125.0},
    {"lat": 35.0, "lon": 124.0},
]
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


def _normalize_longitude(longitude):
    return ((float(longitude) + 180.0) % 360.0) - 180.0


def _initial_bearing_deg(origin, destination):
    origin_lat = math.radians(origin["lat"])
    destination_lat = math.radians(destination["lat"])
    longitude_delta = math.radians(
        _normalize_longitude(destination["lon"] - origin["lon"])
    )
    y = math.sin(longitude_delta) * math.cos(destination_lat)
    x = (
        math.cos(origin_lat) * math.sin(destination_lat)
        - math.sin(origin_lat)
        * math.cos(destination_lat)
        * math.cos(longitude_delta)
    )
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _bearing_difference_deg(left, right):
    return abs((float(left) - float(right) + 180.0) % 360.0 - 180.0)


def _project_point(origin, bearing_deg, distance_nm):
    angular_distance = float(distance_nm) / 3440.065
    bearing = math.radians(float(bearing_deg))
    origin_latitude = math.radians(origin["lat"])
    origin_longitude = math.radians(origin["lon"])
    latitude = math.asin(
        math.sin(origin_latitude) * math.cos(angular_distance)
        + math.cos(origin_latitude)
        * math.sin(angular_distance)
        * math.cos(bearing)
    )
    longitude = origin_longitude + math.atan2(
        math.sin(bearing)
        * math.sin(angular_distance)
        * math.cos(origin_latitude),
        math.cos(angular_distance)
        - math.sin(origin_latitude) * math.sin(latitude),
    )
    return {
        "lat": math.degrees(latitude),
        "lon": _normalize_longitude(math.degrees(longitude)),
    }


def _interpolate_edge(origin, destination, segment_count):
    if segment_count <= 1:
        return [origin, destination]

    distance_nm = calculate_great_circle_distance_nm(
        origin["lat"],
        origin["lon"],
        destination["lat"],
        destination["lon"],
    )
    bearing = _initial_bearing_deg(origin, destination)
    return [
        origin,
        *[
            _project_point(
                origin,
                bearing,
                distance_nm * index / segment_count,
            )
            for index in range(1, segment_count)
        ],
        destination,
    ]


def _linear_interpolate_edge(origin, destination, segment_count):
    longitude_delta = _normalize_longitude(destination["lon"] - origin["lon"])
    return [
        {
            "lat": origin["lat"]
            + (destination["lat"] - origin["lat"]) * index / segment_count,
            "lon": _normalize_longitude(
                origin["lon"] + longitude_delta * index / segment_count
            ),
        }
        for index in range(segment_count + 1)
    ]


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


def _uses_controlled_maritime_passage(line):
    return any(
        LineString(passage["coordinates"])
        .buffer(passage["width_degrees"])
        .covers(line)
        for passage in MARITIME_PASSAGES
    )


def _edge_is_navigable(origin, destination, land_data):
    line = _line(origin, destination)
    if not land_data["prepared"].intersects(line):
        return True
    if _uses_controlled_maritime_passage(line):
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


def _route_is_navigable(points, land_data):
    return all(
        _edge_is_navigable(start, end, land_data)
        for start, end in zip(points, points[1:])
    )


def _course_aware_route_points(route_points, current_cog, land_data):
    course = _to_float(current_cog)
    if course is None or not route_points or len(route_points) < 2:
        return route_points, False

    course %= 360.0
    route_distance = _route_distance_nm(route_points)
    if route_distance < COURSE_WAYPOINT_MIN_ROUTE_NM:
        return route_points, False

    origin = route_points[0]
    first_target = route_points[1]
    route_bearing = _initial_bearing_deg(origin, first_target)
    if (
        _bearing_difference_deg(course, route_bearing)
        > COURSE_WAYPOINT_MAX_HEADING_DIFFERENCE_DEG
    ):
        return route_points, False

    first_leg_distance = calculate_great_circle_distance_nm(
        origin["lat"],
        origin["lon"],
        first_target["lat"],
        first_target["lon"],
    )
    waypoint_distance = min(
        COURSE_WAYPOINT_MAX_DISTANCE_NM,
        max(
            COURSE_WAYPOINT_MIN_DISTANCE_NM,
            route_distance * COURSE_WAYPOINT_DISTANCE_RATIO,
        ),
        first_leg_distance * 0.45,
    )
    if waypoint_distance < 0.5:
        return route_points, False

    waypoint = _project_point(origin, course, waypoint_distance)
    candidate = [origin, waypoint, *route_points[1:]]
    if not _route_is_navigable(candidate, land_data):
        return route_points, False
    if _route_distance_nm(candidate) > route_distance * COURSE_WAYPOINT_MAX_DETOUR_RATIO:
        return route_points, False
    return candidate, True


def _densify_route_points(
    route_points,
    land_data,
    spacing_nm=ROUTE_POINT_SPACING_NM,
):
    if len(route_points) < 2:
        return route_points

    route_distance = _route_distance_nm(route_points)
    effective_spacing = max(
        float(spacing_nm),
        route_distance / MAX_INTERPOLATED_SEGMENTS
        if route_distance
        else float(spacing_nm),
    )
    densified = [route_points[0]]
    for origin, destination in zip(route_points, route_points[1:]):
        edge_distance = calculate_great_circle_distance_nm(
            origin["lat"],
            origin["lon"],
            destination["lat"],
            destination["lon"],
        )
        segment_count = max(1, math.ceil(edge_distance / effective_spacing))
        edge_points = _interpolate_edge(origin, destination, segment_count)
        if not _route_is_navigable(edge_points, land_data):
            # The anchor edge was checked in lon/lat space. At high latitudes a
            # great-circle interpolation can bow onto land, so retain the safe
            # anchor geometry while still returning a renderable multi-point line.
            edge_points = _linear_interpolate_edge(
                origin,
                destination,
                segment_count,
            )
        densified.extend(edge_points[1:])
    return densified


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
    current_cog=None,
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
        route_points, course_waypoint_applied = _course_aware_route_points(
            [
                origin,
                destination,
            ],
            current_cog,
            land_data,
        )
        route_points = _densify_route_points(route_points, land_data)
        route_distance = _route_distance_nm(route_points)
        return {
            "status": "estimated",
            "route_method": (
                "course_aware_sea_route_baseline"
                if course_waypoint_applied
                else "geodesic_sea_route_baseline"
            ),
            "distance_method": (
                "course_aware_navigable_route_baseline"
                if course_waypoint_applied
                else "navigable_route_baseline"
            ),
            "great_circle_distance_nm": great_circle_distance,
            "navigable_distance_nm": route_distance,
            "route_distance_ratio": (
                route_distance / great_circle_distance
                if great_circle_distance
                else 1.0
            ),
            "estimated_route_geojson": _route_geojson(route_points),
            "course_waypoint_applied": course_waypoint_applied,
            "route_point_count": len(route_points),
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
    maritime_corridor_applied = False
    if not route_points:
        route_points = _shortest_visible_route(
            [
                origin,
                destination,
                *GLOBAL_MARITIME_WAYPOINTS,
            ],
            land_data,
        )
        maritime_corridor_applied = bool(route_points)
    if not route_points:
        corridor_route = _verified_corridor_route(
            origin,
            destination,
            land_data,
        )
        if corridor_route:
            route_points, course_waypoint_applied = _course_aware_route_points(
                corridor_route["route_points"],
                current_cog,
                land_data,
            )
            route_points = _densify_route_points(route_points, land_data)
            route_distance = _route_distance_nm(route_points)
            return {
                "status": "estimated",
                "route_method": (
                    "course_aware_land_avoidance_baseline"
                    if course_waypoint_applied
                    else "land_avoidance_baseline"
                ),
                "distance_method": (
                    "course_aware_navigable_route_baseline"
                    if course_waypoint_applied
                    else "navigable_route_baseline"
                ),
                "great_circle_distance_nm": great_circle_distance,
                "navigable_distance_nm": route_distance,
                "route_distance_ratio": (
                    route_distance / great_circle_distance
                    if great_circle_distance
                    else 1.0
                ),
                "estimated_route_geojson": _route_geojson(route_points),
                "course_waypoint_applied": course_waypoint_applied,
                "route_point_count": len(route_points),
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
            "course_waypoint_applied": False,
            "route_point_count": 2,
            "warnings": [
                "navigable_route_unavailable",
            ],
        }

    route_points, course_waypoint_applied = _course_aware_route_points(
        route_points,
        current_cog,
        land_data,
    )
    route_points = _densify_route_points(route_points, land_data)
    route_distance = _route_distance_nm(route_points)
    return {
        "status": "estimated",
        "route_method": (
            "course_aware_maritime_corridor_baseline"
            if course_waypoint_applied and maritime_corridor_applied
            else (
                "course_aware_land_avoidance_baseline"
                if course_waypoint_applied
                else (
                    "maritime_corridor_baseline"
                    if maritime_corridor_applied
                    else "land_avoidance_baseline"
                )
            )
        ),
        "distance_method": (
            "course_aware_navigable_route_baseline"
            if course_waypoint_applied
            else "navigable_route_baseline"
        ),
        "great_circle_distance_nm": great_circle_distance,
        "navigable_distance_nm": route_distance,
        "route_distance_ratio": (
            route_distance / great_circle_distance
            if great_circle_distance
            else 1.0
        ),
        "estimated_route_geojson": _route_geojson(route_points),
        "course_waypoint_applied": course_waypoint_applied,
        "route_point_count": len(route_points),
        "warnings": (
            ["strategic_maritime_corridor_applied"]
            if maritime_corridor_applied
            else []
        ),
    }

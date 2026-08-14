from __future__ import annotations

from risk_monitor.navigation.eta_engine import calculate_great_circle_distance_nm
from risk_monitor.navigation.route_engine import (
    DEFAULT_LAND_MASK_PATH,
    _edge_is_navigable,
    load_land_geometries,
)


SHIPPING_LANE_ROUTE_METHOD = "shipping_lane_prior_baseline"
MAX_PRIOR_ROUTE_DISTANCE_RATIO = 1.35


def _route_coordinates(route_geojson):
    if not isinstance(route_geojson, dict):
        return None
    if route_geojson.get("type") != "LineString":
        return None

    coordinates = route_geojson.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return None
    return coordinates


def _point(lat, lon):
    return {
        "lat": float(lat),
        "lon": float(lon),
    }


def _origin_destination(origin, destination, baseline_route):
    if origin and destination:
        return (
            _point(origin["lat"], origin["lon"]),
            _point(destination["lat"], destination["lon"]),
        )

    coordinates = _route_coordinates(baseline_route.get("estimated_route_geojson"))
    if not coordinates:
        return None, None
    start = coordinates[0]
    end = coordinates[-1]
    return _point(start[1], start[0]), _point(end[1], end[0])


def _bbox_intersects_route(bbox, route_coordinates):
    if not bbox or not route_coordinates:
        return False

    min_lon = min(coordinate[0] for coordinate in route_coordinates)
    max_lon = max(coordinate[0] for coordinate in route_coordinates)
    min_lat = min(coordinate[1] for coordinate in route_coordinates)
    max_lat = max(coordinate[1] for coordinate in route_coordinates)
    return not (
        max_lat < bbox["min_lat"]
        or min_lat > bbox["max_lat"]
        or max_lon < bbox["min_lon"]
        or min_lon > bbox["max_lon"]
    )


def _feature_coordinates(feature):
    geometry = feature.get("geometry") or {}
    if geometry.get("type") != "LineString":
        return []

    coordinates = geometry.get("coordinates") or []
    return [
        coordinate
        for coordinate in coordinates
        if isinstance(coordinate, list)
        and len(coordinate) >= 2
        and coordinate[0] is not None
        and coordinate[1] is not None
    ]


def _candidate_waypoints(origin, destination, baseline_coordinates, lane_features):
    waypoints = []
    used_feature_ids = []

    for feature in lane_features or []:
        if feature.get("type") not in {
            "traffic_lane",
            "traffic_separation_scheme",
            "recommended_track",
            "deep_water_route",
            "route_density_corridor",
        }:
            continue
        if not _bbox_intersects_route(feature.get("bbox"), baseline_coordinates):
            continue

        coordinates = _feature_coordinates(feature)
        if len(coordinates) < 2:
            continue
        first_distance = calculate_great_circle_distance_nm(
            origin["lat"],
            origin["lon"],
            coordinates[0][1],
            coordinates[0][0],
        )
        last_distance = calculate_great_circle_distance_nm(
            origin["lat"],
            origin["lon"],
            coordinates[-1][1],
            coordinates[-1][0],
        )
        if last_distance < first_distance:
            coordinates = list(reversed(coordinates))

        for longitude, latitude in coordinates:
            min_lon = min(origin["lon"], destination["lon"]) - 2.0
            max_lon = max(origin["lon"], destination["lon"]) + 2.0
            min_lat = min(origin["lat"], destination["lat"]) - 2.0
            max_lat = max(origin["lat"], destination["lat"]) + 2.0
            if not min_lon <= longitude <= max_lon:
                continue
            if not min_lat <= latitude <= max_lat:
                continue
            waypoints.append(_point(latitude, longitude))
        used_feature_ids.append(feature.get("id"))

    deduped = []
    seen = set()
    for waypoint in waypoints:
        key = (round(waypoint["lat"], 4), round(waypoint["lon"], 4))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(waypoint)
    return deduped, used_feature_ids


def _baseline_tail_after_lane(baseline_coordinates, lane_waypoints, destination):
    if not lane_waypoints:
        return []

    last_lane = lane_waypoints[-1]
    route_direction = 1 if destination["lon"] >= lane_waypoints[0]["lon"] else -1
    tail = []
    for longitude, latitude in baseline_coordinates[1:-1]:
        if route_direction < 0 and longitude >= last_lane["lon"]:
            continue
        if route_direction > 0 and longitude <= last_lane["lon"]:
            continue
        tail.append(_point(latitude, longitude))
    return tail


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


def _route_is_navigable(points, land_mask_path):
    land_data = load_land_geometries(land_mask_path)
    return all(
        _edge_is_navigable(start, end, land_data)
        for start, end in zip(points, points[1:])
    )


def _fallback(baseline_route, reason):
    return {
        **baseline_route,
        "status": "fallback",
        "route_method": baseline_route.get("route_method"),
        "candidate_route_method": baseline_route.get("route_method"),
        "shipping_lane_prior_applied": False,
        "warnings": [
            *(baseline_route.get("warnings") or []),
            reason,
        ],
    }


def apply_shipping_lane_prior(
    baseline_route,
    origin=None,
    destination=None,
    lane_features=None,
    land_mask_path=DEFAULT_LAND_MASK_PATH,
):
    baseline_route = baseline_route or {}
    baseline_geojson = baseline_route.get("estimated_route_geojson")
    baseline_coordinates = _route_coordinates(baseline_geojson)
    if not baseline_coordinates:
        return _fallback(baseline_route, "malformed_baseline_route")

    origin, destination = _origin_destination(origin, destination, baseline_route)
    if not origin or not destination:
        return _fallback(baseline_route, "missing_origin_or_destination")

    waypoints, used_feature_ids = _candidate_waypoints(
        origin,
        destination,
        baseline_coordinates,
        lane_features,
    )
    if not waypoints:
        return _fallback(baseline_route, "no_applicable_shipping_lane_prior")

    baseline_tail = _baseline_tail_after_lane(
        baseline_coordinates,
        waypoints,
        destination,
    )
    candidate_points = [
        origin,
        *waypoints,
        *baseline_tail,
        destination,
    ]
    great_circle_distance = calculate_great_circle_distance_nm(
        origin["lat"],
        origin["lon"],
        destination["lat"],
        destination["lon"],
    )
    candidate_distance = _route_distance_nm(candidate_points)
    baseline_distance = (
        baseline_route.get("navigable_distance_nm")
        or candidate_distance
    )
    if candidate_distance < great_circle_distance:
        return _fallback(baseline_route, "candidate_shorter_than_great_circle")
    if candidate_distance > baseline_distance * MAX_PRIOR_ROUTE_DISTANCE_RATIO:
        return _fallback(baseline_route, "candidate_excessive_detour")
    if not _route_is_navigable(candidate_points, land_mask_path):
        return _fallback(baseline_route, "candidate_intersects_land")

    return {
        **baseline_route,
        "status": "estimated",
        "route_method": SHIPPING_LANE_ROUTE_METHOD,
        "candidate_route_method": SHIPPING_LANE_ROUTE_METHOD,
        "distance_method": "navigable_route_with_shipping_lane_prior",
        "estimated_route_geojson": _route_geojson(candidate_points),
        "great_circle_distance_nm": great_circle_distance,
        "navigable_distance_nm": candidate_distance,
        "route_distance_ratio": (
            candidate_distance / great_circle_distance
            if great_circle_distance
            else 1.0
        ),
        "shipping_lane_prior_applied": True,
        "shipping_lane_feature_ids": used_feature_ids,
        "warnings": [
            *(baseline_route.get("warnings") or []),
            "shipping_lane_prior_poc_not_for_navigation",
        ],
    }

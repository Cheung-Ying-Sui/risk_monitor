from __future__ import annotations

import math

from shapely.geometry import LineString, shape

from risk_monitor.navigation.eta_engine import calculate_great_circle_distance_nm
from risk_monitor.navigation.route_monitor import calculate_distance_to_route


TRAFFIC_LANE_OVERLAP_WEIGHT = 35.0
RECOMMENDED_TRACK_WEIGHT = 25.0
DEEP_WATER_ROUTE_WEIGHT = 15.0
CONSTRAINT_WEIGHT = 10.0
DISTANCE_EFFICIENCY_WEIGHT = 15.0
RECOMMENDED_TRACK_PROXIMITY_THRESHOLD_NM = 12.0
PRECAUTIONARY_AREA_PENALTY = 3.0
BOUNDARY_CROSSING_PENALTY = 5.0
EXCESSIVE_DETOUR_RATIO = 1.35

POSITIVE_AREA_TYPES = {
    "traffic_lane",
    "recommended_track",
    "deep_water_route",
}
PRECAUTIONARY_TYPES = {
    "precautionary_area",
}
CONTEXT_LINE_TYPES = {
    "other",
    "traffic_separation_scheme_boundary",
    "traffic_separation_line",
}
PROXIMITY_LINE_TYPES = {
    "recommended_track",
    "deep_water_route",
}


def _to_float(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
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
    normalized = []
    for coordinate in coordinates:
        if not isinstance(coordinate, (list, tuple)) or len(coordinate) < 2:
            return None
        longitude = _to_float(coordinate[0])
        latitude = _to_float(coordinate[1])
        if latitude is None or longitude is None:
            return None
        normalized.append([longitude, latitude])
    return normalized


def _route_distance_nm_from_coordinates(coordinates):
    total = 0.0
    for start, end in zip(coordinates, coordinates[1:]):
        total += calculate_great_circle_distance_nm(
            start[1],
            start[0],
            end[1],
            end[0],
        )
    return total


def _geometry_kind(feature):
    return feature.get("geometry_kind") or (feature.get("properties") or {}).get(
        "geometry_kind"
    )


def _routeing_type(feature):
    return (
        feature.get("routeing_type")
        or feature.get("type")
        or (feature.get("properties") or {}).get("routeing_type")
        or "other"
    )


def _feature_id(feature):
    return (
        feature.get("id")
        or feature.get("feature_id")
        or (feature.get("properties") or {}).get("feature_id")
    )


def _feature_name(feature):
    return feature.get("name") or (feature.get("properties") or {}).get("name")


def _line_length_nm(geometry):
    if geometry.is_empty:
        return 0.0
    if geometry.geom_type == "LineString":
        return _route_distance_nm_from_coordinates(list(geometry.coords))
    if geometry.geom_type == "MultiLineString":
        return sum(_line_length_nm(part) for part in geometry.geoms)
    if geometry.geom_type == "GeometryCollection":
        return sum(_line_length_nm(part) for part in geometry.geoms)
    return 0.0


def _feature_shape(feature):
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        return None
    try:
        shaped = shape(geometry)
    except Exception:
        return None
    if shaped.is_empty:
        return None
    return shaped


def _line_proximity_nm(route_geojson, feature):
    geometry = feature.get("geometry") or {}
    if geometry.get("type") != "LineString":
        return None
    feature_route = {
        "type": "LineString",
        "coordinates": geometry.get("coordinates") or [],
    }
    route_coordinates = _route_coordinates(route_geojson)
    if not route_coordinates:
        return None

    distances = [
        calculate_distance_to_route(
            {
                "latitude": coordinate[1],
                "longitude": coordinate[0],
            },
            feature_route,
        )
        for coordinate in route_coordinates
    ]
    distances = [distance for distance in distances if distance is not None]
    if not distances:
        return None
    return sum(distances) / len(distances)


def _distance_efficiency_score(route_distance_nm, great_circle_distance_nm):
    if not route_distance_nm or not great_circle_distance_nm:
        return 0.0
    ratio = route_distance_nm / great_circle_distance_nm
    if ratio <= 1.0:
        return DISTANCE_EFFICIENCY_WEIGHT
    if ratio >= EXCESSIVE_DETOUR_RATIO:
        return 0.0
    return DISTANCE_EFFICIENCY_WEIGHT * (
        1.0 - ((ratio - 1.0) / (EXCESSIVE_DETOUR_RATIO - 1.0))
    )


def _score_from_ratio(ratio, weight):
    return max(0.0, min(weight, ratio * weight))


def evaluate_route_corridor(candidate_route_geojson, official_routeing_features):
    route_coordinates = _route_coordinates(candidate_route_geojson)
    if not route_coordinates:
        return {
            "status": "unavailable",
            "route_distance_nm": None,
            "official_area_overlap_distance_nm": None,
            "official_area_overlap_ratio": None,
            "traffic_lane_overlap_distance_nm": None,
            "recommended_track_proximity_nm": None,
            "precautionary_area_distance_nm": None,
            "routeing_score": None,
            "traffic_lane_score": None,
            "recommended_track_score": None,
            "constraint_score": None,
            "distance_efficiency_score": None,
            "matched_features": [],
            "warnings": ["missing_or_malformed_route"],
        }

    route_line = LineString(route_coordinates)
    route_distance_nm = _route_distance_nm_from_coordinates(route_coordinates)
    great_circle_distance_nm = calculate_great_circle_distance_nm(
        route_coordinates[0][1],
        route_coordinates[0][0],
        route_coordinates[-1][1],
        route_coordinates[-1][0],
    )
    if not official_routeing_features:
        distance_efficiency_score = _distance_efficiency_score(
            route_distance_nm,
            great_circle_distance_nm,
        )
        return {
            "status": "evaluated",
            "route_distance_nm": route_distance_nm,
            "official_area_overlap_distance_nm": 0.0,
            "official_area_overlap_ratio": 0.0,
            "traffic_lane_overlap_distance_nm": 0.0,
            "recommended_track_proximity_nm": None,
            "precautionary_area_distance_nm": 0.0,
            "routeing_score": distance_efficiency_score,
            "traffic_lane_score": 0.0,
            "recommended_track_score": 0.0,
            "constraint_score": CONSTRAINT_WEIGHT,
            "distance_efficiency_score": distance_efficiency_score,
            "matched_features": [],
            "warnings": ["no_routeing_data"],
        }

    official_area_overlap_distance_nm = 0.0
    traffic_lane_overlap_distance_nm = 0.0
    recommended_area_overlap_distance_nm = 0.0
    deep_water_overlap_distance_nm = 0.0
    precautionary_area_distance_nm = 0.0
    recommended_proximities = []
    boundary_crossings = 0
    matched_features = []
    warnings = []

    for feature in official_routeing_features:
        shaped = _feature_shape(feature)
        if shaped is None:
            warnings.append("invalid_routeing_feature_geometry")
            continue

        routeing_type = _routeing_type(feature)
        geometry_kind = _geometry_kind(feature)
        geometry_type = (feature.get("geometry") or {}).get("type")
        matched = False
        if geometry_type in {"Polygon", "MultiPolygon"}:
            overlap_distance = _line_length_nm(route_line.intersection(shaped))
            if overlap_distance > 0:
                official_area_overlap_distance_nm += overlap_distance
                matched = True
                if routeing_type == "traffic_lane":
                    traffic_lane_overlap_distance_nm += overlap_distance
                elif routeing_type == "recommended_track":
                    recommended_area_overlap_distance_nm += overlap_distance
                elif routeing_type == "deep_water_route":
                    deep_water_overlap_distance_nm += overlap_distance
                elif routeing_type in PRECAUTIONARY_TYPES:
                    precautionary_area_distance_nm += overlap_distance
        elif geometry_type == "LineString":
            proximity = _line_proximity_nm(candidate_route_geojson, feature)
            if routeing_type in PROXIMITY_LINE_TYPES and proximity is not None:
                recommended_proximities.append(proximity)
                if proximity <= RECOMMENDED_TRACK_PROXIMITY_THRESHOLD_NM:
                    matched = True
            if routeing_type in CONTEXT_LINE_TYPES and route_line.crosses(shaped):
                boundary_crossings += 1
                matched = True
        if matched:
            matched_features.append(
                {
                    "id": _feature_id(feature),
                    "name": _feature_name(feature),
                    "routeing_type": routeing_type,
                    "geometry_kind": geometry_kind,
                }
            )

    official_area_overlap_ratio = (
        official_area_overlap_distance_nm / route_distance_nm
        if route_distance_nm
        else 0.0
    )
    traffic_lane_ratio = (
        traffic_lane_overlap_distance_nm / route_distance_nm
        if route_distance_nm
        else 0.0
    )
    recommended_area_ratio = (
        recommended_area_overlap_distance_nm / route_distance_nm
        if route_distance_nm
        else 0.0
    )
    deep_water_ratio = (
        deep_water_overlap_distance_nm / route_distance_nm
        if route_distance_nm
        else 0.0
    )
    recommended_track_proximity_nm = (
        min(recommended_proximities)
        if recommended_proximities
        else None
    )

    traffic_lane_score = _score_from_ratio(
        traffic_lane_ratio,
        TRAFFIC_LANE_OVERLAP_WEIGHT,
    )
    recommended_area_score = _score_from_ratio(
        recommended_area_ratio,
        RECOMMENDED_TRACK_WEIGHT,
    )
    proximity_score = 0.0
    if recommended_track_proximity_nm is not None:
        proximity_score = RECOMMENDED_TRACK_WEIGHT * max(
            0.0,
            1.0
            - recommended_track_proximity_nm / RECOMMENDED_TRACK_PROXIMITY_THRESHOLD_NM,
        )
    recommended_track_score = max(recommended_area_score, proximity_score)
    deep_water_score = _score_from_ratio(
        deep_water_ratio,
        DEEP_WATER_ROUTE_WEIGHT,
    )
    constraint_score = max(
        0.0,
        CONSTRAINT_WEIGHT
        - PRECAUTIONARY_AREA_PENALTY
        * (1.0 if precautionary_area_distance_nm > 0 else 0.0)
        - BOUNDARY_CROSSING_PENALTY * boundary_crossings,
    )
    distance_efficiency_score = _distance_efficiency_score(
        route_distance_nm,
        great_circle_distance_nm,
    )
    routeing_score = max(
        0.0,
        min(
            100.0,
            traffic_lane_score
            + recommended_track_score
            + deep_water_score
            + constraint_score
            + distance_efficiency_score,
        ),
    )

    return {
        "status": "evaluated",
        "route_distance_nm": route_distance_nm,
        "official_area_overlap_distance_nm": official_area_overlap_distance_nm,
        "official_area_overlap_ratio": official_area_overlap_ratio,
        "traffic_lane_overlap_distance_nm": traffic_lane_overlap_distance_nm,
        "recommended_track_proximity_nm": recommended_track_proximity_nm,
        "precautionary_area_distance_nm": precautionary_area_distance_nm,
        "routeing_score": routeing_score,
        "traffic_lane_score": traffic_lane_score,
        "recommended_track_score": recommended_track_score,
        "constraint_score": constraint_score,
        "distance_efficiency_score": distance_efficiency_score,
        "boundary_crossings": boundary_crossings,
        "matched_features": matched_features,
        "warnings": warnings,
    }


def rank_route_candidates(route_candidates, official_routeing_features):
    ranked = []
    for index, candidate in enumerate(route_candidates or []):
        route_geojson = candidate.get("estimated_route_geojson") or candidate.get(
            "route_geojson"
        )
        score = evaluate_route_corridor(
            route_geojson,
            official_routeing_features,
        )
        ranked.append(
            {
                "rank": None,
                "candidate_id": candidate.get("candidate_id") or f"candidate_{index}",
                "candidate": candidate,
                "routeing_score": score,
            }
        )

    ranked.sort(
        key=lambda item: (
            item["routeing_score"].get("routeing_score") is not None,
            item["routeing_score"].get("routeing_score") or 0,
            -(
                item["routeing_score"].get("route_distance_nm")
                or float("inf")
            ),
        ),
        reverse=True,
    )
    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank
    return ranked

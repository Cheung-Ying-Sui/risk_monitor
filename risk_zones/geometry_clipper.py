"""Conservative geometry clipping helpers for risk zones."""

from __future__ import annotations

from typing import Any

from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import split


class GeometryClipError(ValueError):
    """Raised when a geometry clipping operation cannot be completed."""


def _expanded_bounds(geometry: BaseGeometry, padding: float = 1.0) -> tuple[float, float, float, float]:
    min_x, min_y, max_x, max_y = geometry.bounds
    return min_x - padding, min_y - padding, max_x + padding, max_y + padding


def _normalize_polygonal_geometry(geometry: BaseGeometry) -> MultiPolygon:
    if isinstance(geometry, Polygon):
        return MultiPolygon([geometry])
    if isinstance(geometry, MultiPolygon):
        return geometry
    if isinstance(geometry, GeometryCollection):
        polygons = []
        for component in geometry.geoms:
            if isinstance(component, Polygon):
                polygons.append(component)
            elif isinstance(component, MultiPolygon):
                polygons.extend(component.geoms)
        if polygons:
            return MultiPolygon(polygons)
    raise GeometryClipError(f"Geometry has no polygonal components: {geometry.geom_type}")


def clip_by_latitude(
    base_geometry: BaseGeometry,
    latitude: float,
    direction: str,
) -> BaseGeometry:
    """Clip geometry north or south of a latitude within the base bounds."""
    min_x, min_y, max_x, max_y = _expanded_bounds(base_geometry)
    if direction == "north_of":
        clipper = box(min_x, latitude, max_x, max_y)
    elif direction == "south_of":
        clipper = box(min_x, min_y, max_x, latitude)
    else:
        raise GeometryClipError(f"Unsupported latitude clip direction: {direction}")
    return base_geometry.intersection(clipper)


def clip_by_longitude(
    base_geometry: BaseGeometry,
    longitude: float,
    direction: str,
) -> BaseGeometry:
    """Clip geometry east or west of a longitude within the base bounds."""
    min_x, min_y, max_x, max_y = _expanded_bounds(base_geometry)
    if direction == "east_of":
        clipper = box(longitude, min_y, max_x, max_y)
    elif direction == "west_of":
        clipper = box(min_x, min_y, longitude, max_y)
    else:
        raise GeometryClipError(f"Unsupported longitude clip direction: {direction}")
    return base_geometry.intersection(clipper)


def clip_by_partial_conditions(
    base_geometry: BaseGeometry,
    partial_conditions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply supported finite-envelope partial boundary conditions in sequence."""
    result = base_geometry
    applied_conditions = []
    warnings = []
    needs_review = False

    for condition in partial_conditions:
        condition_type = condition.get("type")
        value = condition.get("value")
        if value is None:
            warnings.append(f"missing_condition_value:{condition_type}")
            needs_review = True
            continue

        before = result
        if condition_type == "north_of_latitude":
            result = clip_by_latitude(result, float(value), "north_of")
        elif condition_type == "south_of_latitude":
            result = clip_by_latitude(result, float(value), "south_of")
        elif condition_type == "east_of_longitude":
            result = clip_by_longitude(result, float(value), "east_of")
        elif condition_type == "west_of_longitude":
            result = clip_by_longitude(result, float(value), "west_of")
        else:
            warnings.append(f"unsupported_partial_condition:{condition_type}")
            needs_review = True
            continue

        if result.is_empty:
            warnings.append(f"partial_condition_empty_result:{condition_type}")
            needs_review = True
        else:
            applied_conditions.append(condition)

        if before.equals(result):
            warnings.append(f"partial_condition_no_effect:{condition_type}")

    return {
        "geometry": result,
        "applied_conditions": applied_conditions,
        "warnings": warnings,
        "needs_review": bool(applied_conditions) or needs_review,
    }


def evaluate_line_split(
    base_geometry: BaseGeometry,
    coordinate_points: list[dict[str, Any]],
    side_hint: str | None = None,
) -> dict[str, Any]:
    """Evaluate whether a point-to-point line split is safe; do not auto-select unsafe sides."""
    if len(coordinate_points) < 2:
        return {
            "geometry": base_geometry,
            "split_applied": False,
            "warnings": ["insufficient_line_points"],
            "needs_review": True,
            "needs_review_reasons": ["unsafe_line_split"],
        }

    line = LineString([(point["lon"], point["lat"]) for point in coordinate_points])
    boundary = base_geometry.boundary
    endpoints = [line.coords[0], line.coords[-1]]
    endpoint_touches = sum(boundary.distance(LineString([point, point])) < 0.05 for point in endpoints)

    if endpoint_touches < 2:
        return {
            "geometry": base_geometry,
            "split_applied": False,
            "warnings": ["line_endpoints_do_not_reliably_touch_base_boundary"],
            "needs_review": True,
            "needs_review_reasons": ["unsafe_line_split"],
        }

    try:
        split_result = split(base_geometry, line)
    except Exception as exc:
        return {
            "geometry": base_geometry,
            "split_applied": False,
            "warnings": [f"line_split_failed:{exc}"],
            "needs_review": True,
            "needs_review_reasons": ["unsafe_line_split"],
        }

    polygonal = _normalize_polygonal_geometry(split_result)
    if len(polygonal.geoms) < 2:
        return {
            "geometry": base_geometry,
            "split_applied": False,
            "warnings": ["line_split_did_not_create_multiple_polygons"],
            "needs_review": True,
            "needs_review_reasons": ["unsafe_line_split"],
        }

    if side_hint not in {"north", "south", "east", "west"}:
        return {
            "geometry": base_geometry,
            "split_applied": False,
            "warnings": ["line_split_side_selection_not_implemented"],
            "needs_review": True,
            "needs_review_reasons": ["unsafe_line_split"],
        }

    return {
        "geometry": base_geometry,
        "split_applied": False,
        "warnings": ["line_split_clear_side_selection_not_implemented"],
        "needs_review": True,
        "needs_review_reasons": ["unsafe_line_split"],
    }

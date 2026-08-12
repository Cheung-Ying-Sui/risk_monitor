"""Validation and regression helpers for risk zone geometries."""

from __future__ import annotations

from typing import Any

from pyproj import Geod
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry


VALIDATOR_VERSION = "v1"
MIN_IHO_CONFIDENCE = 0.9
MIN_LLM_CONFIDENCE = 0.75
GEOD = Geod(ellps="WGS84")


def _iter_polygon_coords(geometry: BaseGeometry):
    if isinstance(geometry, Polygon):
        polygons = [geometry]
    elif isinstance(geometry, MultiPolygon):
        polygons = list(geometry.geoms)
    else:
        polygons = []

    for polygon in polygons:
        for lon, lat in polygon.exterior.coords:
            yield lon, lat
        for interior in polygon.interiors:
            for lon, lat in interior.coords:
                yield lon, lat


def _coordinate_range_valid(geometry: BaseGeometry) -> bool:
    for lon, lat in _iter_polygon_coords(geometry):
        if lon < -180 or lon > 180 or lat < -90 or lat > 90:
            return False
    return True


def _polygon_closed(geometry: BaseGeometry) -> bool:
    polygons = list(geometry.geoms) if isinstance(geometry, MultiPolygon) else []
    for polygon in polygons:
        if list(polygon.exterior.coords)[0] != list(polygon.exterior.coords)[-1]:
            return False
        for interior in polygon.interiors:
            coords = list(interior.coords)
            if coords[0] != coords[-1]:
                return False
    return True


def geodesic_area_sq_km(geometry: BaseGeometry) -> float:
    """Compute geodesic polygon area in square kilometers."""
    area_sq_m, _ = GEOD.geometry_area_perimeter(geometry)
    return abs(area_sq_m) / 1_000_000


def _iho_match_status(iho_matches: list[dict[str, Any]]) -> str:
    if not iho_matches:
        return "not_provided"
    if any(not match.get("matched") for match in iho_matches):
        return "unmatched"
    if any(float(match.get("confidence") or 0) < MIN_IHO_CONFIDENCE for match in iho_matches):
        return "low_confidence"
    return "matched"


def validate_geometry_result(
    build_result: dict[str, Any],
    previous_geometry: BaseGeometry | None = None,
    llm_confidence: float | None = None,
) -> dict[str, Any]:
    """Validate a geometry builder result and return a database-ready result object."""
    warnings = list(build_result.get("warnings") or [])
    hard_fail_reasons = list(build_result.get("hard_fail_reasons") or [])
    needs_review_reasons = list(build_result.get("needs_review_reasons") or [])

    geometry = build_result.get("geometry")
    geometry_exists = geometry is not None
    geometry_empty = True
    geometry_valid = False
    geometry_type = None
    geometry_type_valid = False
    coordinate_range_valid = False
    polygon_closed = False
    multipolygon_preserved = False
    area_sq_km = 0.0
    area_change_ratio = None

    if not geometry_exists:
        hard_fail_reasons.append("geometry_missing")
    else:
        geometry_empty = geometry.is_empty
        geometry_valid = geometry.is_valid
        geometry_type = geometry.geom_type
        geometry_type_valid = isinstance(geometry, MultiPolygon)
        coordinate_range_valid = _coordinate_range_valid(geometry)
        polygon_closed = _polygon_closed(geometry) if geometry_type_valid else False
        multipolygon_preserved = geometry_type_valid
        area_sq_km = geodesic_area_sq_km(geometry) if not geometry_empty else 0.0

        if geometry_empty:
            hard_fail_reasons.append("geometry_empty")
        if not geometry_valid:
            hard_fail_reasons.append("geometry_invalid")
        if not geometry_type_valid:
            hard_fail_reasons.append("geometry_type_not_multipolygon")
        if not coordinate_range_valid:
            hard_fail_reasons.append("coordinate_range_invalid")
        if not polygon_closed:
            hard_fail_reasons.append("polygon_not_closed")
        if area_sq_km <= 0:
            hard_fail_reasons.append("area_zero")

        if previous_geometry is not None and area_sq_km > 0:
            previous_area_sq_km = geodesic_area_sq_km(previous_geometry)
            if previous_area_sq_km > 0:
                area_change_ratio = abs(area_sq_km - previous_area_sq_km) / previous_area_sq_km
                if area_change_ratio > 0.3:
                    needs_review_reasons.append("area_change_ratio_exceeds_threshold")

    iho_matches = build_result.get("iho_matches") or []
    iho_status = _iho_match_status(iho_matches)
    if iho_status in {"unmatched", "low_confidence"}:
        needs_review_reasons.append(f"iho_match_status:{iho_status}")

    if llm_confidence is not None and llm_confidence < MIN_LLM_CONFIDENCE:
        needs_review_reasons.append("llm_confidence_below_threshold")

    if build_result.get("needs_review"):
        needs_review_reasons.extend(build_result.get("needs_review_reasons") or [])

    hard_fail_reasons = sorted(set(hard_fail_reasons))
    needs_review_reasons = sorted(set(needs_review_reasons))

    if hard_fail_reasons:
        status = "rejected"
        decision = "hard_fail"
    elif needs_review_reasons:
        status = "needs_review"
        decision = "manual_review_required"
    else:
        status = "validated"
        decision = "auto_validated"

    return {
        "summary": {
            "status": status,
            "decision": decision,
            "validator_version": VALIDATOR_VERSION,
        },
        "geometry": {
            "geometry_valid": geometry_valid,
            "geometry_type": geometry_type,
            "geometry_type_valid": geometry_type_valid,
            "geometry_empty": geometry_empty,
            "coordinate_range_valid": coordinate_range_valid,
            "polygon_closed": polygon_closed,
            "multipolygon_preserved": multipolygon_preserved,
            "area_sq_km": area_sq_km,
            "area_change_ratio": area_change_ratio,
        },
        "source_extraction": {
            "iho_match_status": iho_status,
            "llm_confidence": llm_confidence,
            "clipping_applied": (build_result.get("clipping") or {}).get("clipping_applied"),
            "clipping_conditions": (build_result.get("clipping") or {}).get("clipping_conditions"),
            "clipping_confidence": (build_result.get("clipping") or {}).get("clipping_confidence"),
            "coastline_anchor_status": (build_result.get("clipping") or {}).get("coastline_anchor_status"),
            "anchor_resolution": (build_result.get("clipping") or {}).get("anchor_resolution"),
        },
        "review": {
            "warnings": warnings,
            "hard_fail_reasons": hard_fail_reasons,
            "needs_review_reasons": needs_review_reasons,
        },
    }


def _polygon_part_count(geometry: BaseGeometry) -> int:
    if isinstance(geometry, Polygon):
        return 1
    if isinstance(geometry, MultiPolygon):
        return len(geometry.geoms)
    return 0


def compare_geometry_with_baseline(
    new_geometry: BaseGeometry,
    baseline_geometry: BaseGeometry,
) -> dict[str, Any]:
    """Compare a new geometry with a historical baseline geometry."""
    new_area = geodesic_area_sq_km(new_geometry)
    baseline_area = geodesic_area_sq_km(baseline_geometry)
    intersection = new_geometry.intersection(baseline_geometry)
    union = new_geometry.union(baseline_geometry)
    symmetric_difference = new_geometry.symmetric_difference(baseline_geometry)

    intersection_area = geodesic_area_sq_km(intersection) if not intersection.is_empty else 0.0
    union_area = geodesic_area_sq_km(union) if not union.is_empty else 0.0
    symmetric_difference_area = (
        geodesic_area_sq_km(symmetric_difference)
        if not symmetric_difference.is_empty
        else 0.0
    )

    return {
        "area_change_ratio": (
            abs(new_area - baseline_area) / baseline_area
            if baseline_area > 0
            else None
        ),
        "intersection_over_union": (
            intersection_area / union_area
            if union_area > 0
            else None
        ),
        "symmetric_difference_ratio": (
            symmetric_difference_area / union_area
            if union_area > 0
            else None
        ),
        "new_bounds": new_geometry.bounds,
        "baseline_bounds": baseline_geometry.bounds,
        "polygon_part_count_new": _polygon_part_count(new_geometry),
        "polygon_part_count_baseline": _polygon_part_count(baseline_geometry),
    }

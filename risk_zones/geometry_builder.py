"""Local Shapely geometry builder for maritime risk zones."""

from __future__ import annotations

from typing import Any

from shapely import make_valid
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from risk_zones.geometry_clipper import clip_by_partial_conditions, evaluate_line_split
from risk_zones.geojson_loader import build_iho_indexes, normalize_name


class GeometryBuildError(ValueError):
    """Raised when a risk zone geometry cannot be built."""


def normalize_polygonal_geometry(geometry: BaseGeometry) -> MultiPolygon:
    """Normalize Polygon-like geometry to a full-fidelity MultiPolygon."""
    if geometry.is_empty:
        raise GeometryBuildError("Geometry is empty")

    if isinstance(geometry, Polygon):
        return MultiPolygon([geometry])

    if isinstance(geometry, MultiPolygon):
        return geometry

    if isinstance(geometry, GeometryCollection):
        polygons: list[Polygon] = []
        for component in geometry.geoms:
            if isinstance(component, Polygon):
                polygons.append(component)
            elif isinstance(component, MultiPolygon):
                polygons.extend(component.geoms)

        if not polygons:
            raise GeometryBuildError("GeometryCollection contains no polygonal components")
        return MultiPolygon(polygons)

    raise GeometryBuildError(f"Unsupported non-polygonal geometry type: {geometry.geom_type}")


def _feature_name(feature: dict[str, Any]) -> str | None:
    props = feature.get("properties") or {}
    value = props.get("name") or props.get("NAME") or props.get("Name")
    return str(value) if value is not None else None


def _feature_id(feature: dict[str, Any]) -> str | None:
    props = feature.get("properties") or {}
    value = (
        props.get("iho_id")
        or props.get("id")
        or props.get("ID")
        or props.get("IHO_ID")
        or feature.get("id")
    )
    return str(value).strip() if value is not None else None


def _matched_result(
    water_body: dict[str, Any],
    feature: dict[str, Any],
    match_method: str,
    confidence: float,
) -> dict[str, Any]:
    return {
        "input_name": water_body.get("name"),
        "input_id": water_body.get("iho_id"),
        "matched": True,
        "matched_feature": feature,
        "matched_name": _feature_name(feature),
        "matched_id": _feature_id(feature),
        "match_method": match_method,
        "confidence": confidence,
    }


def match_iho_water_body(
    water_body: dict[str, Any],
    iho_indexes: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    """Match a named water body using exact IHO ID, then exact normalized name."""
    body_id = water_body.get("iho_id")
    if body_id is not None:
        feature = iho_indexes.get("by_id", {}).get(str(body_id).strip())
        if feature is not None:
            return _matched_result(water_body, feature, "iho_id_exact", 1.0)

    normalized = normalize_name(water_body.get("name"))
    if normalized:
        feature = iho_indexes.get("by_normalized_name", {}).get(normalized)
        if feature is not None:
            return _matched_result(water_body, feature, "name_exact", 0.95)

    return {
        "input_name": water_body.get("name"),
        "input_id": water_body.get("iho_id"),
        "matched": False,
        "matched_feature": None,
        "matched_name": None,
        "matched_id": None,
        "match_method": "unmatched",
        "confidence": 0.0,
    }


def _validate_lon_lat(point: Any, index: int) -> tuple[float, float]:
    if not isinstance(point, (list, tuple)) or len(point) < 2:
        raise GeometryBuildError(f"Boundary point {index} must contain [lon, lat]")

    lon = float(point[0])
    lat = float(point[1])
    if lon < -180 or lon > 180:
        raise GeometryBuildError(f"Boundary point {index} longitude out of range: {lon}")
    if lat < -90 or lat > 90:
        raise GeometryBuildError(f"Boundary point {index} latitude out of range: {lat}")
    return lon, lat


def build_boundary_polygon(boundary_polygon: list[Any]) -> Polygon:
    """Build a valid Shapely Polygon from GeoJSON-style polygon coordinates."""
    if not boundary_polygon or not isinstance(boundary_polygon, list):
        raise GeometryBuildError("boundary_polygon must be a non-empty GeoJSON-style polygon")

    exterior = boundary_polygon[0]
    if not isinstance(exterior, list):
        raise GeometryBuildError("boundary_polygon exterior ring must be a list")

    ring = [_validate_lon_lat(point, index) for index, point in enumerate(exterior)]
    unique_points = set(ring)
    if len(unique_points) < 3:
        raise GeometryBuildError("Boundary polygon requires at least 3 distinct points")

    if ring[0] != ring[-1]:
        ring.append(ring[0])

    polygon = Polygon(ring)
    if polygon.is_empty:
        raise GeometryBuildError("Boundary polygon is empty")
    if polygon.area == 0:
        raise GeometryBuildError("Boundary polygon area is zero")

    if not polygon.is_valid:
        repaired = make_valid(polygon)
        try:
            repaired_polygonal = normalize_polygonal_geometry(repaired)
        except GeometryBuildError as exc:
            raise GeometryBuildError(f"Boundary polygon is invalid and cannot be repaired: {exc}") from exc

        if len(repaired_polygonal.geoms) != 1:
            raise GeometryBuildError("Boundary polygon repair produced multiple polygon components")
        polygon = repaired_polygonal.geoms[0]

    if not polygon.is_valid:
        raise GeometryBuildError("Boundary polygon remains invalid after repair")
    return polygon


def _shape_feature_geometry(feature: dict[str, Any]) -> BaseGeometry:
    geometry = feature.get("geometry")
    if not geometry:
        raise GeometryBuildError("Matched IHO feature does not contain geometry")
    return shape(geometry)


def _build_method(used_iho: bool, used_boundary: bool, exclude_12nm: bool) -> str:
    parts = []
    if used_iho:
        parts.append("iho_union")
    if used_boundary:
        parts.append("intersect_boundary" if used_iho else "boundary_only")
    if exclude_12nm:
        parts.append("exclude_12nm_requested")
    return "_".join(parts) if parts else "none"


def build_maritime_zone_geometry(
    zone: dict[str, Any],
    iho_feature_collection: dict[str, Any],
    land_mask: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a maritime risk zone geometry from normalized zone input."""
    del land_mask  # Reserved for a later 12nm coastal exclusion implementation.

    warnings: list[str] = []
    hard_fail_reasons: list[str] = []
    needs_review_reasons: list[str] = list(
        zone.get("boundary_parser_needs_review_reasons") or []
    )
    warnings.extend(zone.get("boundary_parser_warnings") or [])
    iho_matches: list[dict[str, Any]] = []
    matched_geometries: list[BaseGeometry] = []

    iho_indexes = build_iho_indexes(iho_feature_collection)

    for water_body in zone.get("named_water_bodies") or []:
        match = match_iho_water_body(water_body, iho_indexes)
        iho_matches.append(match)
        if match.get("matched"):
            matched_geometries.append(_shape_feature_geometry(match["matched_feature"]))
        else:
            needs_review_reasons.append(
                f"unmatched_iho_water_body:{water_body.get('name') or water_body.get('iho_id')}"
            )

    iho_union = unary_union(matched_geometries) if matched_geometries else None

    boundary = None
    if zone.get("boundary_polygon"):
        boundary = build_boundary_polygon(zone["boundary_polygon"])

    used_iho = iho_union is not None and not iho_union.is_empty
    used_boundary = boundary is not None

    if used_iho and used_boundary:
        result = iho_union.intersection(boundary)
    elif used_iho:
        result = iho_union
    elif used_boundary:
        result = boundary
        needs_review_reasons.append("boundary_only")
    else:
        hard_fail_reasons.append("no_geometry_inputs")
        raise GeometryBuildError("Cannot build geometry: no_geometry_inputs")

    if zone.get("exclude_12nm_coastal_waters"):
        warnings.append("12nm coastal exclusion not implemented in phase 2.5.4.4.2")
        needs_review_reasons.append("exclude_12nm_not_implemented")

    geometry = normalize_polygonal_geometry(result)

    clipping_result = None
    partial_conditions = (
        zone.get("boundary_conditions", {}).get("partial_conditions")
        if isinstance(zone.get("boundary_conditions"), dict)
        else []
    )
    if used_iho and partial_conditions:
        clipping_result = clip_by_partial_conditions(geometry, partial_conditions)
        geometry = normalize_polygonal_geometry(clipping_result["geometry"])
        warnings.extend(clipping_result["warnings"])
        needs_review_reasons.append("clipping_applied_needs_review")
        if clipping_result["needs_review"]:
            needs_review_reasons.append("partial_condition_clipping_needs_review")

    line_split_result = None
    coordinate_points = zone.get("boundary_points_parsed") or []
    if used_iho and coordinate_points and not used_boundary:
        line_split_result = evaluate_line_split(geometry, coordinate_points)
        warnings.extend(line_split_result["warnings"])
        if line_split_result["needs_review"]:
            needs_review_reasons.extend(line_split_result["needs_review_reasons"])

    anchor_resolution = zone.get("anchor_resolution") or {}
    if anchor_resolution.get("needs_review"):
        needs_review_reasons.append("anchor_resolution_needs_review")
    if any(anchor.get("manual_verified") for anchor in anchor_resolution.get("anchors", [])):
        needs_review_reasons.append("manual_anchor_used")

    if geometry.is_empty:
        hard_fail_reasons.append("result_geometry_empty")
        raise GeometryBuildError("Result geometry is empty")

    return {
        "geometry": geometry,
        "geometry_geojson": mapping(geometry),
        "iho_matches": iho_matches,
        "warnings": warnings,
        "hard_fail_reasons": hard_fail_reasons,
        "needs_review": bool(needs_review_reasons),
        "needs_review_reasons": needs_review_reasons,
        "build_method": _build_method(
            used_iho,
            used_boundary,
            bool(zone.get("exclude_12nm_coastal_waters")),
        ),
        "clipping": {
            "clipping_applied": bool(
                clipping_result and clipping_result["applied_conditions"]
            ),
            "clipping_conditions": (
                clipping_result["applied_conditions"] if clipping_result else []
            ),
            "clipping_confidence": 0.7
            if clipping_result and clipping_result["applied_conditions"]
            else None,
            "line_split_evaluated": line_split_result is not None,
            "line_split_applied": bool(
                line_split_result and line_split_result["split_applied"]
            ),
            "coastline_anchor_status": "required_unresolved"
            if anchor_resolution.get("needs_review") or "requires_coastline_geometry" in needs_review_reasons
            else "not_required",
            "anchor_resolution": anchor_resolution,
        },
        "source_components": {
            "used_iho_union": used_iho,
            "used_boundary_polygon": used_boundary,
            "used_12nm_exclusion": False,
        },
    }

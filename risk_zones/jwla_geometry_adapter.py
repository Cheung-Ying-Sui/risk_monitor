"""Adapter from current JWLA parser output to geometry builder input."""

from __future__ import annotations

import re
from typing import Any

from risk_zones.jwla_boundary_parser import (
    build_boundary_from_explicit_lines,
    parse_explicit_lines,
)


def _slugify(value: str) -> str:
    normalized = value.lower().strip()
    normalized = normalized.replace("/", " ")
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = re.sub(r"-+", "-", normalized)
    return normalized.strip("-")


def adapt_jwla_zone(zone: dict[str, Any]) -> dict[str, Any]:
    """Convert one current JWLA zone object into the geometry builder contract."""
    warnings: list[str] = []
    components = zone.get("components") or {}
    zone_name = zone.get("zone_name") or "Unnamed Zone"

    named_water_bodies = components.get("named_water_bodies")
    if named_water_bodies is None:
        named_water_bodies = []
        warnings.append("missing_named_water_bodies")
    elif not named_water_bodies:
        warnings.append("empty_named_water_bodies")

    boundary_polygon = (
        components.get("jwc_boundary_polygon")
        or components.get("boundary_polygon")
        or None
    )
    if not boundary_polygon:
        warnings.append("missing_boundary_polygon")

    explicit_lines = components.get("explicit_lines") or []
    if not explicit_lines:
        warnings.append("missing_explicit_lines")

    parsed_lines = parse_explicit_lines(explicit_lines)
    boundary_from_lines = build_boundary_from_explicit_lines(explicit_lines)

    raw_text = "\n".join(explicit_lines).strip()
    if not raw_text:
        warnings.append("missing_raw_text")

    if not boundary_polygon and boundary_from_lines["boundary_polygon"]:
        boundary_polygon = boundary_from_lines["boundary_polygon"]

    return {
        "zone_name": zone_name,
        "zone_slug": f"jwla-{_slugify(zone_name)}",
        "zone_type": "maritime",
        "source": "JWLA",
        "named_water_bodies": named_water_bodies,
        "boundary_polygon": boundary_polygon,
        "boundary_points_raw": explicit_lines,
        "boundary_points_parsed": parsed_lines["coordinate_points"],
        "boundary_conditions": {
            "partial_conditions": parsed_lines["partial_conditions"],
            "text_conditions": parsed_lines["text_conditions"],
            "anchor_conditions": parsed_lines["anchor_conditions"],
        },
        "boundary_parser_confidence": boundary_from_lines["confidence"],
        "boundary_parser_warnings": parsed_lines["warnings"],
        "boundary_parser_needs_review": boundary_from_lines["needs_review"],
        "boundary_parser_needs_review_reasons": boundary_from_lines[
            "needs_review_reasons"
        ],
        "exclude_12nm_coastal_waters": bool(
            components.get("exclude_12nm_coastal_waters", False)
        ),
        "raw_text": raw_text,
        "adapter_warnings": warnings,
    }

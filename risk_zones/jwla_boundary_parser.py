"""Boundary coordinate parser for JWLA explicit line text."""

from __future__ import annotations

import re
from typing import Any

from risk_zones.anchor_resolver import detect_anchor_conditions


HEMISPHERES = "NSEW"
COASTLINE_TERMS = (
    "coast",
    "coastline",
    "border",
    "bay",
    "baía",
    "cape",
    "peninsula",
    "territorial waters",
    "12 nautical",
    "12nm",
    "12 nm",
)

COORDINATE_PATTERN = re.compile(
    r"""
    (?P<degrees>\d{1,3})
    \s*(?:°|º|deg|degrees|\s)
    \s*
    (?:(?P<minutes>\d{1,2}(?:\.\d+)?)\s*(?:'|’|′|min|minutes)?)?
    \s*
    (?:(?P<seconds>\d{1,2}(?:\.\d+)?)\s*(?:"|”|″|sec|seconds)?)?
    \s*
    (?P<hemisphere>[NSEW])
    """,
    re.IGNORECASE | re.VERBOSE,
)


def parse_coordinate_component(text: str) -> dict[str, Any] | None:
    """Parse one latitude or longitude DMS component into decimal degrees."""
    match = COORDINATE_PATTERN.search(text)
    if not match:
        return None

    hemisphere = match.group("hemisphere").upper()
    degrees = float(match.group("degrees"))
    minutes = float(match.group("minutes") or 0)
    seconds = float(match.group("seconds") or 0)

    if hemisphere not in HEMISPHERES:
        return None
    if minutes >= 60 or seconds >= 60:
        return None
    if hemisphere in {"N", "S"} and degrees > 90:
        return None
    if hemisphere in {"E", "W"} and degrees > 180:
        return None

    value = degrees + minutes / 60 + seconds / 3600
    if hemisphere in {"S", "W"}:
        value = -value

    return {
        "value": value,
        "hemisphere": hemisphere,
        "degrees": degrees,
        "minutes": minutes,
        "seconds": seconds,
        "raw": match.group(0),
        "start": match.start(),
        "end": match.end(),
    }


def _component_kind(component: dict[str, Any]) -> str:
    return "lat" if component["hemisphere"] in {"N", "S"} else "lon"


def _extract_components(text: str) -> list[dict[str, Any]]:
    components = []
    for match in COORDINATE_PATTERN.finditer(text):
        parsed = parse_coordinate_component(match.group(0))
        if parsed:
            parsed["start"] = match.start()
            parsed["end"] = match.end()
            components.append(parsed)
    return components


def extract_coordinate_pairs(text: str) -> list[dict[str, Any]]:
    """Extract explicit lat/lon coordinate pairs from text as [lon, lat]."""
    components = _extract_components(text)
    pairs = []
    index = 0

    while index < len(components) - 1:
        first = components[index]
        second = components[index + 1]
        first_kind = _component_kind(first)
        second_kind = _component_kind(second)

        if first_kind != second_kind:
            lat_component = first if first_kind == "lat" else second
            lon_component = first if first_kind == "lon" else second
            pairs.append(
                {
                    "lon": lon_component["value"],
                    "lat": lat_component["value"],
                    "raw": text[first["start"] : second["end"]],
                    "confidence": 0.95,
                    "components": {
                        "lat": lat_component,
                        "lon": lon_component,
                    },
                }
            )
            index += 2
        else:
            index += 1

    return pairs


def _partial_condition_from_component(
    text: str,
    component: dict[str, Any],
) -> dict[str, Any] | None:
    lower_text = text.lower()
    kind = _component_kind(component)

    before = lower_text[max(0, component["start"] - 80) : component["start"]]
    direction = None
    for candidate in ("north of", "south of", "east of", "west of"):
        if candidate in before:
            direction = candidate.replace(" of", "")

    if not direction:
        if "south of latitude" in lower_text and kind == "lat":
            direction = "south"
        elif "north of latitude" in lower_text and kind == "lat":
            direction = "north"
        elif "east of longitude" in lower_text and kind == "lon":
            direction = "east"
        elif "west of longitude" in lower_text and kind == "lon":
            direction = "west"

    if not direction:
        return None

    if kind == "lat" and direction in {"north", "south"}:
        condition_type = f"{direction}_of_latitude"
    elif kind == "lon" and direction in {"east", "west"}:
        condition_type = f"{direction}_of_longitude"
    else:
        return None

    return {
        "type": condition_type,
        "value": component["value"],
        "raw": text,
    }


def parse_explicit_lines(explicit_lines: list[str]) -> dict[str, Any]:
    """Parse JWLA explicit boundary lines into points and non-polygon conditions."""
    coordinate_points: list[dict[str, Any]] = []
    partial_conditions: list[dict[str, Any]] = []
    text_conditions: list[dict[str, Any]] = []
    anchor_conditions: list[dict[str, Any]] = []
    warnings: list[str] = []

    for line in explicit_lines:
        pairs = extract_coordinate_pairs(line)
        coordinate_points.extend(pairs)

        components = _extract_components(line)
        paired_ranges = []
        for pair in pairs:
            lat_component = pair["components"]["lat"]
            lon_component = pair["components"]["lon"]
            paired_ranges.append(
                (
                    min(lat_component["start"], lon_component["start"]),
                    max(lat_component["end"], lon_component["end"]),
                )
            )
        for component in components:
            is_paired = any(start <= component["start"] <= end for start, end in paired_ranges)
            if not is_paired:
                condition = _partial_condition_from_component(line, component)
                if condition:
                    partial_conditions.append(condition)
                else:
                    partial_conditions.append(
                        {
                            "type": f"{_component_kind(component)}_only",
                            "value": component["value"],
                            "raw": line,
                        }
                    )

        lower_line = line.lower()
        anchor_conditions.extend(detect_anchor_conditions(line))
        if any(term in lower_line for term in COASTLINE_TERMS):
            text_conditions.append(
                {
                    "type": "requires_coastline_geometry",
                    "raw": line,
                }
            )
        if any(token in lower_line for token in ("northwest", "northeast", "southwest", "southeast")):
            text_conditions.append(
                {
                    "type": "directional_boundary_description",
                    "raw": line,
                }
            )

    if not coordinate_points:
        warnings.append("no_coordinate_pairs_found")

    confidence = 0.0
    if coordinate_points:
        confidence = 0.6
    if len(coordinate_points) >= 3:
        confidence = 0.75
    if partial_conditions or text_conditions:
        confidence = min(confidence, 0.65)

    return {
        "coordinate_points": coordinate_points,
        "partial_conditions": partial_conditions,
        "text_conditions": text_conditions,
        "anchor_conditions": anchor_conditions,
        "warnings": warnings,
        "confidence": confidence,
    }


def build_boundary_from_explicit_lines(explicit_lines: list[str]) -> dict[str, Any]:
    """Build a boundary polygon only when explicit lines are self-contained."""
    parsed = parse_explicit_lines(explicit_lines)
    points = parsed["coordinate_points"]
    needs_review_reasons = []

    requires_coastline = any(
        condition["type"] == "requires_coastline_geometry"
        for condition in parsed["text_conditions"]
    )
    if requires_coastline:
        needs_review_reasons.append("requires_coastline_geometry")
    if parsed["partial_conditions"]:
        needs_review_reasons.append("contains_partial_boundary_conditions")
    if len(points) < 3:
        needs_review_reasons.append("insufficient_coordinate_points")

    buildable = not needs_review_reasons and len(points) >= 3
    boundary_polygon = None
    if buildable:
        ring = [[point["lon"], point["lat"]] for point in points]
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        boundary_polygon = [ring]

    return {
        "boundary_polygon": boundary_polygon,
        "boundary_points": points,
        "partial_conditions": parsed["partial_conditions"],
        "text_conditions": parsed["text_conditions"],
        "anchor_conditions": parsed["anchor_conditions"],
        "warnings": parsed["warnings"],
        "buildable": buildable,
        "confidence": parsed["confidence"] if buildable else min(parsed["confidence"], 0.65),
        "needs_review": bool(needs_review_reasons),
        "needs_review_reasons": needs_review_reasons,
    }

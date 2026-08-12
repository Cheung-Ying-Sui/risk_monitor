"""Validation helpers for manually verified anchor overrides."""

from __future__ import annotations

from typing import Any


VALID_ANCHOR_TYPES = {
    "bay",
    "cape",
    "peninsula",
    "coastline_point",
    "coastal_border_point",
}


def validate_anchor_override(anchor: dict[str, Any]) -> dict[str, Any]:
    """Validate one manual anchor override record."""
    errors: list[str] = []
    warnings: list[str] = []

    if not str(anchor.get("canonical_name") or "").strip():
        errors.append("canonical_name_required")

    if anchor.get("anchor_type") not in VALID_ANCHOR_TYPES:
        errors.append("anchor_type_invalid")

    longitude = anchor.get("longitude")
    if longitude is None:
        errors.append("longitude_required")
    else:
        try:
            value = float(longitude)
            if value < -180 or value > 180:
                errors.append("longitude_out_of_range")
        except (TypeError, ValueError):
            errors.append("longitude_invalid")

    latitude = anchor.get("latitude")
    if latitude is None:
        errors.append("latitude_required")
    else:
        try:
            value = float(latitude)
            if value < -90 or value > 90:
                errors.append("latitude_out_of_range")
        except (TypeError, ValueError):
            errors.append("latitude_invalid")

    if not str(anchor.get("source_name") or "").strip():
        errors.append("source_name_required")
    if not str(anchor.get("source_reference") or "").strip():
        errors.append("source_reference_required")
    if anchor.get("verification_status") != "manual_verified":
        errors.append("verification_status_must_be_manual_verified")
    if not str(anchor.get("verified_at") or "").strip():
        errors.append("verified_at_required")
    if not str(anchor.get("verified_by") or "").strip():
        errors.append("verified_by_required")

    aliases = anchor.get("aliases", [])
    if aliases is not None and not isinstance(aliases, list):
        errors.append("aliases_must_be_list")

    if not str(anchor.get("country") or "").strip():
        warnings.append("country_missing")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
    }

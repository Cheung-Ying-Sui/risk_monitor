"""Build review queues for unresolved JWLA boundary anchors."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REVIEW_DECISIONS = {"pending", "verified", "rejected", "deferred"}


def make_review_id(source: str, zone_name: str, anchor_name: str, anchor_type: str) -> str:
    """Create a deterministic review identifier."""
    key = "|".join(
        [
            source.strip().lower(),
            zone_name.strip().lower(),
            anchor_name.strip().lower(),
            anchor_type.strip().lower(),
        ]
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def suggested_action_for_anchor(anchor: dict[str, Any]) -> str:
    status = anchor.get("status")
    anchor_type = anchor.get("anchor_type")
    warnings = anchor.get("warnings") or []

    if status == "manual_required" and "manual_anchor_missing" in warnings:
        return "manual_coordinate_verification"
    if status == "manual_required":
        return "verify_named_anchor"
    if status == "ambiguous" and anchor_type == "country_coastline":
        return "resolve_with_coastline_gis"
    if status == "unresolved" and anchor_type == "country_border":
        return "add_complete_country_boundary_data"
    if status == "unresolved":
        return "resolve_missing_reference_data"
    return "review_anchor"


def _candidate_geometries(anchor: dict[str, Any]) -> list[dict[str, Any]]:
    geometry = anchor.get("geometry")
    if not geometry:
        return []
    return [
        {
            "geometry_type": anchor.get("geometry_type"),
            "geometry": geometry,
            "resolution_method": anchor.get("resolution_method"),
            "confidence": anchor.get("confidence"),
            "source": anchor.get("source"),
        }
    ]


def build_pending_anchor_review(
    zone_results: list[dict[str, Any]],
    source_document: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic pending anchor review queue from zone results."""
    source = "JWLA"
    items_by_id: dict[str, dict[str, Any]] = {}

    for zone_result in zone_results:
        zone_name = zone_result.get("zone_name") or ""
        for anchor in zone_result.get("anchor_statuses") or []:
            status = anchor.get("status")
            if status == "resolved":
                continue

            anchor_name = anchor.get("query_name") or anchor.get("anchor_name") or ""
            anchor_type = anchor.get("anchor_type") or ""
            review_id = make_review_id(source, zone_name, anchor_name, anchor_type)
            reason = ", ".join(anchor.get("warnings") or [])

            item = {
                "review_id": review_id,
                "source": source,
                "source_document": source_document,
                "zone_name": zone_name,
                "anchor_name": anchor_name,
                "anchor_type": anchor_type,
                "status": status,
                "raw_text": anchor.get("raw_text"),
                "reason": reason,
                "suggested_action": suggested_action_for_anchor(anchor),
                "candidate_geometries": _candidate_geometries(anchor),
                "review": {
                    "decision": "pending",
                    "longitude": None,
                    "latitude": None,
                    "canonical_name": None,
                    "source_name": None,
                    "source_reference": None,
                    "verified_by": None,
                    "verified_at": None,
                    "notes": None,
                },
            }
            items_by_id.setdefault(review_id, item)

    items = sorted(items_by_id.values(), key=lambda item: item["review_id"])
    return {
        "schema_version": "1.0",
        "source": source,
        "source_document": source_document,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pending_count": len(items),
        "items": items,
    }


def validate_review_decision(item: dict[str, Any]) -> dict[str, Any]:
    """Validate whether a review item is complete enough for future override import."""
    errors = []
    review = item.get("review") or {}
    decision = review.get("decision")

    if decision not in REVIEW_DECISIONS:
        errors.append("decision_invalid")
    if decision == "verified":
        for field in (
            "longitude",
            "latitude",
            "source_name",
            "source_reference",
            "verified_by",
            "verified_at",
        ):
            if review.get(field) in (None, ""):
                errors.append(f"{field}_required_for_verified")

        longitude = review.get("longitude")
        latitude = review.get("latitude")
        if longitude not in (None, ""):
            try:
                value = float(longitude)
                if value < -180 or value > 180:
                    errors.append("longitude_out_of_range")
            except (TypeError, ValueError):
                errors.append("longitude_invalid")
        if latitude not in (None, ""):
            try:
                value = float(latitude)
                if value < -90 or value > 90:
                    errors.append("latitude_out_of_range")
            except (TypeError, ValueError):
                errors.append("latitude_invalid")

    return {
        "valid": not errors,
        "errors": errors,
    }


def write_review_json(review_queue: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(review_queue, file, ensure_ascii=False, indent=2)


def write_review_csv(review_queue: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    fieldnames = [
        "review_id",
        "zone_name",
        "anchor_name",
        "anchor_type",
        "status",
        "reason",
        "suggested_action",
        "raw_text",
        "decision",
        "longitude",
        "latitude",
        "source_name",
        "source_reference",
        "verified_by",
        "verified_at",
        "notes",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for item in review_queue.get("items") or []:
            review = item.get("review") or {}
            writer.writerow(
                {
                    "review_id": item.get("review_id"),
                    "zone_name": item.get("zone_name"),
                    "anchor_name": item.get("anchor_name"),
                    "anchor_type": item.get("anchor_type"),
                    "status": item.get("status"),
                    "reason": item.get("reason"),
                    "suggested_action": item.get("suggested_action"),
                    "raw_text": item.get("raw_text"),
                    "decision": review.get("decision"),
                    "longitude": review.get("longitude"),
                    "latitude": review.get("latitude"),
                    "source_name": review.get("source_name"),
                    "source_reference": review.get("source_reference"),
                    "verified_by": review.get("verified_by"),
                    "verified_at": review.get("verified_at"),
                    "notes": review.get("notes"),
                }
            )

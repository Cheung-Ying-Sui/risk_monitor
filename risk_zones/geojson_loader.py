"""GeoJSON loading helpers for risk zone geometry processing."""

from __future__ import annotations

import json
import re
import string
from pathlib import Path
from typing import Any


def load_geojson(path: str | Path) -> dict[str, Any]:
    """Load a GeoJSON document from disk."""
    geojson_path = Path(path)
    if not geojson_path.exists():
        raise FileNotFoundError(f"GeoJSON file does not exist: {geojson_path}")
    if not geojson_path.is_file():
        raise ValueError(f"GeoJSON path is not a file: {geojson_path}")

    try:
        with geojson_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in GeoJSON file {geojson_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"GeoJSON root must be an object: {geojson_path}")
    return data


def load_iho_seas(path: str | Path) -> dict[str, Any]:
    """Load the local IHO seas FeatureCollection."""
    data = load_geojson(path)
    if data.get("type") != "FeatureCollection":
        raise ValueError("IHO seas GeoJSON must be a FeatureCollection")
    if not isinstance(data.get("features"), list):
        raise ValueError("IHO seas GeoJSON must contain a features array")
    return data


def normalize_name(name: str | None) -> str:
    """Normalize a feature or water-body name for exact matching."""
    if not name:
        return ""

    punctuation_to_space = string.punctuation.replace("-", "")
    translation = str.maketrans({char: " " for char in punctuation_to_space})
    normalized = name.lower().strip().translate(translation)
    normalized = normalized.replace("-", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def build_iho_indexes(feature_collection: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    """Build exact-match IHO lookup indexes by ID and normalized name."""
    by_id: dict[str, dict[str, Any]] = {}
    by_normalized_name: dict[str, dict[str, Any]] = {}

    for feature in feature_collection.get("features", []):
        if not isinstance(feature, dict):
            continue

        props = feature.get("properties") or {}
        raw_id = (
            props.get("iho_id")
            or props.get("id")
            or props.get("ID")
            or props.get("IHO_ID")
            or feature.get("id")
        )
        if raw_id is not None:
            by_id[str(raw_id).strip()] = feature

        raw_name = props.get("name") or props.get("NAME") or props.get("Name")
        normalized_name = normalize_name(str(raw_name) if raw_name is not None else None)
        if normalized_name:
            by_normalized_name[normalized_name] = feature

    return {
        "by_id": by_id,
        "by_normalized_name": by_normalized_name,
    }


def load_land_mask(path: str | Path) -> dict[str, Any]:
    """Load the local land mask FeatureCollection."""
    data = load_geojson(path)
    if data.get("type") != "FeatureCollection":
        raise ValueError("Land mask GeoJSON must be a FeatureCollection")
    if not isinstance(data.get("features"), list):
        raise ValueError("Land mask GeoJSON must contain a features array")
    return data

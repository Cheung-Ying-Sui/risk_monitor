from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


DEFAULT_SHIPPING_LANE_PATH = (
    Path(__file__).resolve().parents[2]
    / "static"
    / "navigation"
    / "processed"
    / "english_channel_routeing_prior.geojson"
)
POC_SHIPPING_LANE_PATH = (
    Path(__file__).resolve().parents[2]
    / "static"
    / "navigation"
    / "uk_routeing_measures_poc.geojson"
)


def _feature_from_geojson(feature):
    properties = feature.get("properties") or {}
    return {
        "id": feature.get("id") or properties.get("feature_id") or properties.get("id"),
        "name": properties.get("name"),
        "type": properties.get("routeing_type") or properties.get("type"),
        "routeing_type": properties.get("routeing_type") or properties.get("type"),
        "geometry_kind": properties.get("geometry_kind"),
        "geometry": feature.get("geometry"),
        "source": properties.get("source_id") or properties.get("source"),
        "source_type": properties.get("source_type"),
        "source_version": properties.get("source_version"),
        "official": bool(properties.get("official")),
        "source_feature_id": properties.get("source_feature_id"),
        "raw_feature_type": properties.get("raw_feature_type"),
        "bbox": properties.get("bbox"),
        "notes": properties.get("notes"),
    }


@lru_cache(maxsize=8)
def load_shipping_lane_reference(path=DEFAULT_SHIPPING_LANE_PATH):
    data_path = Path(path)
    data = json.loads(data_path.read_text(encoding="utf-8"))
    if data.get("type") != "FeatureCollection":
        raise ValueError("shipping lane reference must be a FeatureCollection.")

    metadata = data.get("metadata") or {}
    return {
        "source": metadata.get("source_id") or metadata.get("source") or "unknown",
        "source_type": metadata.get("dataset_type"),
        "source_version": metadata.get("source_version") or "unknown",
        "source_notes": metadata.get("source_notes"),
        "official": bool(metadata.get("official")),
        "features": [
            _feature_from_geojson(feature)
            for feature in data.get("features") or []
            if isinstance(feature, dict)
        ],
    }


def load_official_routeing_reference():
    return load_shipping_lane_reference(DEFAULT_SHIPPING_LANE_PATH)


def load_poc_shipping_lane_reference():
    return load_shipping_lane_reference(POC_SHIPPING_LANE_PATH)

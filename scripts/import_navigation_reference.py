from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = PROJECT_ROOT / "static" / "navigation" / "raw"
DEFAULT_PROCESSED_DIR = PROJECT_ROOT / "static" / "navigation" / "processed"
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "static" / "navigation" / "source_manifest.json"
ENGLISH_CHANNEL_BBOX = {
    "min_lon": -8.5,
    "min_lat": 48.0,
    "max_lon": 3.5,
    "max_lat": 51.8,
}

SOURCE = {
    "source_id": "ukho_routeing_measures",
    "publisher": "UK Hydrographic Office",
    "dataset_name": "Ships Routeing Measures",
    "dataset_type": "official_routeing_measure",
    "source_url": (
        "https://datahub.admiralty.co.uk/server/rest/services/Hosted/"
        "Ships_Routeing_Measures/FeatureServer"
    ),
    "source_version": "ArcGIS item modified 2025-08-13; annual update cadence",
    "licence": "Open Government Licence v3.0",
    "geographic_coverage": "UK EEZ; processed subset: English Channel and Western Approaches",
    "processing_method": (
        "Filter raw UKHO IMO Routeing Measures Points/Lines/Areas to the POC bbox, "
        "normalize feature properties, validate WGS84 GeoJSON geometry, and keep "
        "areas/lines/points separate. Polygon boundaries are not converted to "
        "route centerlines."
    ),
    "original_file": [
        "raw/ukho_routeing_measures_points.geojson",
        "raw/ukho_routeing_measures_lines.geojson",
        "raw/ukho_routeing_measures_areas.geojson",
    ],
    "processed_file": "processed/english_channel_routeing_prior.geojson",
}

RAW_FILES = {
    "point": "ukho_routeing_measures_points.geojson",
    "line": "ukho_routeing_measures_lines.geojson",
    "area": "ukho_routeing_measures_areas.geojson",
}

TYPE_MAP = {
    "traffic separation scheme lanes": "traffic_lane",
    "traffic separation scheme boundaries": "other",
    "traffic separation lines": "other",
    "traffic separation zones": "other",
    "recommended routes": "recommended_track",
    "deep water route part": "deep_water_route",
    "precautionary areas": "precautionary_area",
    "inshore traffic zones": "other",
    "areas to be avoided": "other",
    "two-way routes": "recommended_track",
}


def _read_geojson(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("type") != "FeatureCollection":
        raise ValueError(f"{path} must be a FeatureCollection.")
    return data


def _iter_positions(geometry):
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Point":
        yield coordinates
    elif geometry_type == "LineString":
        yield from coordinates or []
    elif geometry_type == "Polygon":
        for ring in coordinates or []:
            yield from ring
    elif geometry_type == "MultiPolygon":
        for polygon in coordinates or []:
            for ring in polygon:
                yield from ring


def _valid_position(position):
    if not isinstance(position, list) or len(position) < 2:
        return False
    longitude, latitude = position[:2]
    if not isinstance(longitude, (int, float)):
        return False
    if not isinstance(latitude, (int, float)):
        return False
    return -180 <= longitude <= 180 and -90 <= latitude <= 90


def _validate_geometry(geometry):
    if not isinstance(geometry, dict):
        return False
    if geometry.get("type") not in {"Point", "LineString", "Polygon", "MultiPolygon"}:
        return False
    positions = list(_iter_positions(geometry))
    return bool(positions) and all(_valid_position(position) for position in positions)


def _geometry_bbox(geometry):
    positions = list(_iter_positions(geometry))
    longitudes = [position[0] for position in positions]
    latitudes = [position[1] for position in positions]
    return {
        "min_lon": min(longitudes),
        "min_lat": min(latitudes),
        "max_lon": max(longitudes),
        "max_lat": max(latitudes),
    }


def _bbox_intersects(left, right):
    return not (
        left["max_lat"] < right["min_lat"]
        or left["min_lat"] > right["max_lat"]
        or left["max_lon"] < right["min_lon"]
        or left["min_lon"] > right["max_lon"]
    )


def _routeing_type(raw_type):
    normalized = str(raw_type or "").strip().lower()
    return TYPE_MAP.get(normalized, normalized or "other")


def _normalize_feature(feature, geometry_kind):
    properties = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    if not _validate_geometry(geometry):
        raise ValueError("invalid or empty geometry")

    source_feature_id = (
        properties.get("globalid")
        or properties.get("fid")
        or feature.get("id")
    )
    feature_type = properties.get("feature_ty")
    feature_id = f"ukho_{geometry_kind}_{source_feature_id}".replace("{", "").replace("}", "")
    bbox = _geometry_bbox(geometry)
    return {
        "type": "Feature",
        "id": feature_id,
        "properties": {
            "feature_id": feature_id,
            "name": properties.get("inform") or str(feature_type or "").strip(),
            "routeing_type": _routeing_type(feature_type),
            "geometry_kind": geometry_kind,
            "source_id": SOURCE["source_id"],
            "source_feature_id": str(source_feature_id),
            "official": True,
            "source_type": SOURCE["dataset_type"],
            "source_version": SOURCE["source_version"],
            "raw_feature_type": feature_type,
            "orientation": properties.get("orient"),
            "bbox": bbox,
        },
        "geometry": geometry,
    }


def build_processed_reference(raw_dir=DEFAULT_RAW_DIR):
    features = []
    seen_ids = {}
    for geometry_kind, file_name in RAW_FILES.items():
        data = _read_geojson(Path(raw_dir) / file_name)
        for feature in data.get("features") or []:
            normalized = _normalize_feature(feature, geometry_kind)
            if not _bbox_intersects(
                normalized["properties"]["bbox"],
                ENGLISH_CHANNEL_BBOX,
            ):
                continue
            feature_id = normalized["properties"]["feature_id"]
            if feature_id in seen_ids:
                seen_ids[feature_id] += 1
                feature_id = f"{feature_id}_{seen_ids[feature_id]}"
                normalized["id"] = feature_id
                normalized["properties"]["feature_id"] = feature_id
            else:
                seen_ids[feature_id] = 1
            features.append(normalized)

    return {
        "type": "FeatureCollection",
        "metadata": {
            "source_id": SOURCE["source_id"],
            "publisher": SOURCE["publisher"],
            "dataset_name": SOURCE["dataset_name"],
            "dataset_type": SOURCE["dataset_type"],
            "source_url": SOURCE["source_url"],
            "source_version": SOURCE["source_version"],
            "licence": SOURCE["licence"],
            "geographic_coverage": SOURCE["geographic_coverage"],
            "processing_method": SOURCE["processing_method"],
            "official": True,
            "crs": "EPSG:4326",
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "poc_bbox": ENGLISH_CHANNEL_BBOX,
        },
        "features": features,
    }


def write_outputs(
    raw_dir=DEFAULT_RAW_DIR,
    processed_dir=DEFAULT_PROCESSED_DIR,
    manifest_path=DEFAULT_MANIFEST_PATH,
):
    processed_dir = Path(processed_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)
    output_path = processed_dir / "english_channel_routeing_prior.geojson"
    processed = build_processed_reference(raw_dir=raw_dir)
    output_path.write_text(
        json.dumps(processed, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    manifest = {
        "sources": [
            {
                **SOURCE,
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "processed_feature_count": len(processed["features"]),
                "official": True,
                "crs": "EPSG:4326",
            }
        ]
    }
    Path(manifest_path).write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {
        "processed_file": str(output_path),
        "manifest_file": str(manifest_path),
        "feature_count": len(processed["features"]),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    parser.add_argument("--processed-dir", default=str(DEFAULT_PROCESSED_DIR))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_PATH))
    args = parser.parse_args()
    result = write_outputs(
        raw_dir=Path(args.raw_dir),
        processed_dir=Path(args.processed_dir),
        manifest_path=Path(args.manifest),
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

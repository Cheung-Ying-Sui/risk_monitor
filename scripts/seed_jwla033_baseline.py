"""Seed JWLA-033 baseline risk geometry.

The default mode is dry-run. Use --apply explicitly to write source, zone,
and a validated zone version through the Supabase service-role client.
"""

import argparse
import hashlib
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from risk_zones.geojson_loader import load_geojson
from risk_zones.geometry_builder import normalize_polygonal_geometry


BASELINE_PATH = Path("JWLA_033/JWLA_033_Risk_Seas_Merge_Layer.json")
SOURCE = "JWLA"
SOURCE_DOCUMENT = "JWLA-033"
ZONE_NAME = "JWLA-033 Listed Areas Baseline"
ZONE_SLUG = "jwla-033-listed-areas-baseline"
SOURCE_URL = "local:JWLA_033/JWLA_033_Risk_Seas_Merge_Layer.json"
PARSER_VERSION = "manual-baseline-v1"


def load_baseline_geometry_geojson():
    baseline = load_geojson(BASELINE_PATH)
    if baseline.get("type") == "GeometryCollection":
        geometries = [shape(item) for item in baseline.get("geometries") or []]
        geometry = normalize_polygonal_geometry(unary_union(geometries))
    else:
        geometry = normalize_polygonal_geometry(shape(baseline))

    return mapping(geometry)


def get_document_hash():
    return hashlib.sha256((REPO_ROOT / BASELINE_PATH).read_bytes()).hexdigest()


def build_seed_payload():
    return {
        "source": SOURCE,
        "source_document": SOURCE_DOCUMENT,
        "source_url": SOURCE_URL,
        "document_hash": get_document_hash(),
        "zone_name": ZONE_NAME,
        "zone_slug": ZONE_SLUG,
        "zone_type": "maritime",
        "source_status": "validated",
        "zone_status": "validated",
        "zone_version_status": "validated",
        "geometry_geojson": load_baseline_geometry_geojson(),
        "confidence": None,
        "validation_result": {
            "source_type": "historical_manual_baseline",
            "manual_baseline": True,
        },
        "notes": "Manual/external GIS baseline fixture. Do not overwrite existing records.",
    }


def _single_row(result, label):
    if not result.data:
        raise RuntimeError(f"{label} did not return a row.")
    return result.data[0]


def _get_or_create_source(client, payload):
    existing = (
        client
        .schema("risk")
        .table("zone_sources")
        .select("id,source,document_hash,status")
        .eq("source", payload["source"])
        .eq("document_hash", payload["document_hash"])
        .limit(1)
        .execute()
    )
    if existing.data:
        return existing.data[0], False

    insert_result = (
        client
        .schema("risk")
        .table("zone_sources")
        .insert(
            {
                "source": payload["source"],
                "source_url": payload["source_url"],
                "source_document": payload["source_document"],
                "document_hash": payload["document_hash"],
                "raw_text": payload["notes"],
                "parser_version": PARSER_VERSION,
                "status": payload["source_status"],
            }
        )
        .execute()
    )
    return _single_row(insert_result, "zone_sources insert"), True


def _get_or_create_zone(client, payload):
    existing = (
        client
        .schema("risk")
        .table("zones")
        .select("id,source,zone_slug,status")
        .eq("source", payload["source"])
        .eq("zone_slug", payload["zone_slug"])
        .limit(1)
        .execute()
    )
    if existing.data:
        return existing.data[0], False

    insert_result = (
        client
        .schema("risk")
        .table("zones")
        .insert(
            {
                "zone_name": payload["zone_name"],
                "zone_slug": payload["zone_slug"],
                "zone_type": payload["zone_type"],
                "source": payload["source"],
                "description": payload["notes"],
                "status": payload["zone_status"],
            }
        )
        .execute()
    )
    return _single_row(insert_result, "zones insert"), True


def _get_or_create_zone_version(client, payload, source_id, zone_id):
    existing = (
        client
        .schema("risk")
        .table("zone_versions")
        .select("id,version_no,status,raw_extraction")
        .eq("zone_id", zone_id)
        .eq("source_id", source_id)
        .execute()
    )
    for row in existing.data or []:
        raw_extraction = row.get("raw_extraction") or {}
        if (
            raw_extraction.get("source_document") == payload["source_document"]
            and raw_extraction.get("document_hash") == payload["document_hash"]
            and raw_extraction.get("seed_slug") == payload["zone_slug"]
        ):
            return row, False

    version_no = max([row["version_no"] for row in existing.data] or [0]) + 1
    insert_result = (
        client
        .schema("risk")
        .table("zone_versions")
        .insert(
            {
                "zone_id": zone_id,
                "source_id": source_id,
                "version_no": version_no,
                "geometry": payload["geometry_geojson"],
                "raw_text": payload["notes"],
                "raw_extraction": {
                    "source_document": payload["source_document"],
                    "document_hash": payload["document_hash"],
                    "seed_slug": payload["zone_slug"],
                    "baseline_path": str(BASELINE_PATH),
                },
                "validation_result": payload["validation_result"],
                "confidence": payload["confidence"],
                "status": payload["zone_version_status"],
            }
        )
        .execute()
    )
    return _single_row(insert_result, "zone_versions insert"), True


def apply_seed(payload):
    try:
        from postgrest.exceptions import APIError
    except ImportError:
        APIError = None

    try:
        from risk_monitor.supabase_client import supabase
    except ImportError as exc:
        raise RuntimeError(
            "supabase_client.py and supabase are required for --apply."
        ) from exc

    supabase.postgrest.timeout = 600
    supabase.postgrest.session.timeout = 600

    try:
        result = (
            supabase
            .schema("tracking")
            .rpc(
                "seed_jwla033_baseline",
                {
                    "p_source": payload["source"],
                    "p_source_url": payload["source_url"],
                    "p_source_document": payload["source_document"],
                    "p_document_hash": payload["document_hash"],
                    "p_zone_name": payload["zone_name"],
                    "p_zone_slug": payload["zone_slug"],
                    "p_zone_type": payload["zone_type"],
                    "p_geometry_geojson": payload["geometry_geojson"],
                    "p_raw_text": payload["notes"],
                    "p_validation_result": payload["validation_result"],
                    "p_parser_version": PARSER_VERSION,
                },
            )
            .execute()
        )
    except Exception as exc:
        if APIError is not None and isinstance(exc, APIError):
            error = getattr(exc, "args", [{}])[0]
            if isinstance(error, dict) and error.get("code") == "PGRST106":
                raise RuntimeError(
                    "Supabase REST API does not expose the required schema. "
                    "Apply 20260812011000_create_jwla033_baseline_seed_rpc.sql "
                    "and use the service-role-only RPC path."
                ) from exc
        raise

    row = _single_row(result, "seed_jwla033_baseline RPC")

    return {
        "source_id": row["source_id"],
        "source_created": row["source_created"],
        "zone_id": row["zone_id"],
        "zone_created": row["zone_created"],
        "zone_version_id": row["zone_version_id"],
        "zone_version_no": row["zone_version_no"],
        "zone_version_status": row["zone_version_status"],
        "zone_version_created": row["zone_version_created"],
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="Seed JWLA-033 baseline risk zone geometry."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and print payload summary without database writes.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Write the validated baseline seed to Supabase.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    payload = build_seed_payload()

    if not args.apply:
        print("JWLA-033 baseline seed dry-run. No database write was performed.")
        print(
            f"source={payload['source']} "
            f"source_document={payload['source_document']} "
            f"zone_slug={payload['zone_slug']} "
            f"document_hash={payload['document_hash']} "
            f"geometry_type={payload['geometry_geojson']['type']} "
            f"zone_version_status={payload['zone_version_status']}"
        )
        return

    result = apply_seed(payload)
    print(
        "JWLA-033 baseline seed applied. "
        "The zone version is validated, not active."
    )
    print(
        f"source_id={result['source_id']} "
        f"source_created={result['source_created']} "
        f"zone_id={result['zone_id']} "
        f"zone_created={result['zone_created']} "
        f"zone_version_id={result['zone_version_id']} "
        f"zone_version_no={result['zone_version_no']} "
        f"zone_version_status={result['zone_version_status']} "
        f"zone_version_created={result['zone_version_created']}"
    )


if __name__ == "__main__":
    main()

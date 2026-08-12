from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from risk_zones.anchor_resolver import load_anchor_overrides, resolve_boundary_anchors
from risk_zones.geojson_loader import load_geojson
from risk_zones.jwla_geometry_adapter import adapt_jwla_zone
from risk_zones.pending_anchor_review import (
    build_pending_anchor_review,
    write_review_csv,
    write_review_json,
)


JWC_ZONES_PATH = Path("risk_zones/jwc_risk_zones.json")
COUNTRIES_PATH = Path("JWLA_033/JWLA_033_countries.json")
ANCHOR_OVERRIDES_PATH = Path("risk_zones/anchor_overrides.json")
OUTPUT_JSON_PATH = Path("risk_zones/pending_anchor_review.json")
OUTPUT_CSV_PATH = Path("risk_zones/pending_anchor_review.csv")
SOURCE_DOCUMENT = "JWLA_033"


def build_zone_results():
    data = load_geojson(JWC_ZONES_PATH)
    countries = load_geojson(COUNTRIES_PATH)
    overrides = load_anchor_overrides(ANCHOR_OVERRIDES_PATH)

    results = []
    for zone in data.get("zones") or []:
        adapted = adapt_jwla_zone(zone)
        anchor_resolution = resolve_boundary_anchors(
            adapted["boundary_conditions"]["anchor_conditions"],
            countries,
            overrides,
        )
        results.append(
            {
                "zone_name": adapted["zone_name"],
                "anchor_statuses": anchor_resolution["anchors"],
            }
        )
    return results


def main():
    review_queue = build_pending_anchor_review(
        build_zone_results(),
        source_document=SOURCE_DOCUMENT,
    )
    write_review_json(review_queue, OUTPUT_JSON_PATH)
    write_review_csv(review_queue, OUTPUT_CSV_PATH)
    print(
        "pending anchor review generated "
        f"json={OUTPUT_JSON_PATH} "
        f"csv={OUTPUT_CSV_PATH} "
        f"pending_count={review_queue['pending_count']}"
    )


if __name__ == "__main__":
    main()

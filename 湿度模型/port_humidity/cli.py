"""Run with: python -m 湿度模型.port_humidity.cli <command>."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from .ingestion import UnverifiedLocationError, WeatherIngestionService
from .open_meteo import DEFAULT_ENDPOINT, OpenMeteoClient
from .quality import evaluate_quality
from .repository import WeatherRepository
from .time_utils import shanghai_period_bounds

SEED_PATH = Path(__file__).resolve().parents[1] / "seed" / "ports.json"
MVP_LOCATION_PATH = Path(__file__).resolve().parents[1] / "seed" / "mvp_approximate_locations.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Port humidity ERA5 Phase-1 data operations")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed", help="idempotently seed six ports and pending analysis points")
    sub.add_parser("seed-mvp-locations", help="idempotently activate five sourced approximate port points")
    verify = sub.add_parser("verify-location", help="record a human-reviewed terminal analysis point")
    verify.add_argument("--port", required=True)
    verify.add_argument("--location-id", required=True)
    verify.add_argument("--name", required=True)
    verify.add_argument("--latitude", required=True, type=float)
    verify.add_argument("--longitude", required=True, type=float)
    verify.add_argument("--coordinate-source", required=True)
    verify.add_argument("--location-description", required=True)
    verify.add_argument("--i-confirm-terminal-point", required=True, action="store_true")
    approximate = sub.add_parser("set-approximate-location", help="activate an MVP-only approximate analysis point")
    approximate.add_argument("--port", required=True)
    approximate.add_argument("--name", required=True)
    approximate.add_argument("--latitude", required=True, type=float)
    approximate.add_argument("--longitude", required=True, type=float)
    approximate.add_argument("--coordinate-source", required=True)
    approximate.add_argument("--description", required=True)
    replace = sub.add_parser("replace-location", help="version the coordinate without rewriting historical rows")
    replace.add_argument("--port", required=True)
    replace.add_argument("--name", required=True)
    replace.add_argument("--latitude", required=True, type=float)
    replace.add_argument("--longitude", required=True, type=float)
    replace.add_argument("--coordinate-source", required=True)
    replace.add_argument("--description", required=True)
    replace.add_argument("--verified", action="store_true", help="only for a reviewed berth/terminal point")
    backfill = sub.add_parser("backfill", help="resume monthly ERA5 backfill")
    scope = backfill.add_mutually_exclusive_group(required=True)
    scope.add_argument("--port")
    scope.add_argument("--all-verified-ports", action="store_true")
    scope.add_argument("--retry-failed", action="store_true")
    backfill.add_argument("--from", dest="start", type=date.fromisoformat)
    backfill.add_argument("--to", dest="end", type=date.fromisoformat)
    backfill.add_argument("--force", action="store_true")
    validate = sub.add_parser("validate", help="reassess persisted UTC hours without fetching")
    validate.add_argument("--port", required=True)
    validate.add_argument("--from", dest="start", required=True, type=date.fromisoformat)
    validate.add_argument("--to", dest="end", required=True, type=date.fromisoformat)
    audit = sub.add_parser("audit-all-ports", help="re-read each local calendar year and persist quality reports")
    audit.add_argument("--from-year", type=int, default=2016)
    audit.add_argument("--to-year", type=int, default=2025)
    sub.add_parser("ports", help="list analysis points and collection state")
    batches = sub.add_parser("batches", help="inspect resumable ingestion attempts")
    batches.add_argument("--port")
    batches.add_argument("--status", choices=("pending", "running", "succeeded", "failed", "partial"))
    batches.add_argument("--limit", type=int, default=100)
    coverage = sub.add_parser("coverage", help="show yearly coverage")
    coverage.add_argument("--port", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    repository = WeatherRepository()
    if args.command == "seed":
        print(json.dumps(repository.seed(SEED_PATH), ensure_ascii=False))
        return 0
    if args.command == "seed-mvp-locations":
        points = json.loads(MVP_LOCATION_PATH.read_text(encoding="utf-8"))
        result = []
        for point in points:
            if point.get("coordinate_system") != "WGS84" or not point.get("source_url", "").startswith("https://"):
                raise ValueError(f"invalid coordinate metadata for {point.get('port_code')}")
            row = repository.set_approximate_location(
                point["port_code"], name=point["name"], latitude=point["latitude"],
                longitude=point["longitude"],
                coordinate_source=f"{point['source_title']}; {point['source_url']}",
                description=point["description"],
            )
            result.append({"port_code": point["port_code"], "location_id": row["id"],
                           "status": row["verification_status"], "is_primary": row["is_primary"]})
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.command == "verify-location":
        row = repository.verify_location(
            args.port, args.location_id, name=args.name, latitude=args.latitude, longitude=args.longitude,
            coordinate_source=args.coordinate_source,
            location_description=args.location_description,
            verified_at=datetime.now(timezone.utc).isoformat(),
        )
        print(json.dumps({"id": row["id"], "verification_status": row["verification_status"],
                          "is_primary": row["is_primary"]}, ensure_ascii=False))
        return 0
    if args.command == "set-approximate-location":
        row = repository.set_approximate_location(
            args.port, name=args.name, latitude=args.latitude, longitude=args.longitude,
            coordinate_source=args.coordinate_source, description=args.description,
        )
        print(json.dumps({"id": row["id"], "verification_status": row["verification_status"],
                          "is_primary": row["is_primary"]}, ensure_ascii=False))
        return 0
    if args.command == "replace-location":
        row = repository.replace_location(
            args.port, name=args.name, latitude=args.latitude, longitude=args.longitude,
            coordinate_source=args.coordinate_source, description=args.description,
            verified=args.verified,
        )
        print(json.dumps({"id": row["id"], "verification_status": row["verification_status"],
                          "is_primary": row["is_primary"]}, ensure_ascii=False))
        return 0
    if args.command == "ports":
        print(json.dumps(repository.list_weather_ports(), ensure_ascii=False, default=str))
        return 0
    if args.command == "batches":
        print(json.dumps(repository.list_batches(port_code=args.port, status=args.status, limit=args.limit), ensure_ascii=False, default=str))
        return 0
    if args.command == "coverage":
        print(json.dumps(repository.get_weather_coverage(args.port), ensure_ascii=False, default=str))
        return 0
    if args.command == "validate":
        location = repository.primary_location(args.port)
        if not location:
            raise UnverifiedLocationError(f"{args.port}: no usable primary analysis point")
        source = repository.source()
        start, end = shanghai_period_bounds(args.start, args.end)
        rows = repository.hourly_rows(location["id"], source["id"], start, end)
        report = evaluate_quality(rows, start, end)
        repository.insert_quality({**report, "weather_location_id": location["id"], "source_id": source["id"]})
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report["status"] == "pass" else 2
    if args.command == "audit-all-ports":
        if args.from_year > args.to_year:
            raise ValueError("from-year must not exceed to-year")
        source = repository.source()
        result = []
        for location in repository.locations(verified_only=True):
            years = []
            for year in range(args.from_year, args.to_year + 1):
                start, end = shanghai_period_bounds(date(year, 1, 1), date(year, 12, 31))
                rows = repository.hourly_rows(location["id"], source["id"], start, end)
                report = evaluate_quality(rows, start, end)
                repository.insert_quality({**report, "weather_location_id": location["id"],
                                           "source_id": source["id"]})
                years.append({"year": year, "expected": report["expected_hours"],
                              "actual": report["actual_distinct_hours"],
                              "complete": report["complete_row_hours"],
                              "missing": report["missing_hours"],
                              "null_rh": report["null_rh_hours"],
                              "invalid": report["invalid_value_hours"],
                              "duplicates": report["details"]["duplicate_hours"],
                              "status": report["status"]})
            result.append({"port_code": location["port"]["port_code"],
                           "location_status": location["verification_status"],
                           "years": years, "expected": sum(y["expected"] for y in years),
                           "actual": sum(y["actual"] for y in years),
                           "complete": sum(y["complete"] for y in years),
                           "status": "pass" if all(y["status"] == "pass" for y in years) else "fail"})
        summary = {"ports": len(result), "expected": sum(p["expected"] for p in result),
                   "actual": sum(p["actual"] for p in result),
                   "complete": sum(p["complete"] for p in result),
                   "status": "pass" if len(result) == 6 and all(p["status"] == "pass" for p in result) else "fail",
                   "results": result}
        print(json.dumps(summary, ensure_ascii=False))
        return 0 if summary["status"] == "pass" else 2
    if args.command == "backfill":
        import os
        client = OpenMeteoClient(endpoint=DEFAULT_ENDPOINT,
                                 timeout=float(os.getenv("OPEN_METEO_TIMEOUT_SECONDS", "30")),
                                 retries=int(os.getenv("OPEN_METEO_RETRIES", "3")))
        service = WeatherIngestionService(repository, client,
                                          grid_warning_km=float(os.getenv("WEATHER_GRID_WARNING_KM", "35")),
                                          interval_seconds=float(os.getenv("OPEN_METEO_INTERVAL_SECONDS", "1")))
        if args.retry_failed:
            results = service.retry_failed()
        else:
            if args.start is None or args.end is None:
                raise ValueError("--from and --to are required unless --retry-failed is used")
            if args.all_verified_ports:
                codes = sorted({item["port"]["port_code"] for item in repository.locations(verified_only=True)})
                if not codes:
                    print(json.dumps({"status": "no_verified_ports", "results": []}))
                    return 2
            else:
                codes = [args.port]
            results = []
            for code in codes:
                results.extend(service.backfill(code, args.start, args.end, force=args.force))
        print(json.dumps(results, ensure_ascii=False, default=str))
        return 2 if any(item["status"] in ("failed", "partial") for item in results) else 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

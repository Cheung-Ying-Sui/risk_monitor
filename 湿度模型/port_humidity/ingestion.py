"""Resumable, idempotent month-wise ERA5 backfill."""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone
from typing import Any, Callable

from .open_meteo import OpenMeteoClient, request_params
from .quality import evaluate_quality, grid_distance_km
from .repository import WeatherRepository
from .time_utils import month_chunks, shanghai_period_bounds, utc_iso

logger = logging.getLogger(__name__)


class UnverifiedLocationError(ValueError):
    pass


class WeatherIngestionService:
    def __init__(self, repository: WeatherRepository, client: OpenMeteoClient,
                 *, grid_warning_km: float = 35, interval_seconds: float = 1,
                 sleep: Callable[[float], None] = time.sleep):
        self.repository = repository
        self.client = client
        self.grid_warning_km = grid_warning_km
        self.interval_seconds = interval_seconds
        self.sleep = sleep

    def backfill(self, port_code: str, start: date, end: date, *, force: bool = False) -> list[dict[str, Any]]:
        location = self.repository.primary_location(port_code)
        if not location or location["verification_status"] not in ("verified", "approximate") or not location["is_primary"]:
            raise UnverifiedLocationError(f"{port_code}: no usable primary analysis point")
        if location.get("requested_latitude") is None or location.get("requested_longitude") is None:
            raise UnverifiedLocationError(f"{port_code}: analysis-point coordinates are missing")
        source = self.repository.source()
        if source.get("model_options", {}).get("models") != "era5" or source.get("dataset") != "era5":
            raise ValueError("weather source must explicitly use ERA5")
        if source.get("api_endpoint") != self.client.endpoint:
            raise ValueError("configured API endpoint does not match the ERA5 source metadata")
        results = []
        for index, (chunk_start, chunk_end) in enumerate(month_chunks(start, end)):
            succeeded = self.repository.latest_batch(location["id"], source["id"], chunk_start, chunk_end, status="succeeded")
            if succeeded and not force:
                results.append({"port_code": port_code, "start_date": chunk_start.isoformat(), "end_date": chunk_end.isoformat(), "status": "skipped_succeeded", "batch_id": succeeded["id"]})
                continue
            if index and self.interval_seconds > 0:
                self.sleep(self.interval_seconds)
            results.append(self._ingest_chunk(location, source, chunk_start, chunk_end))
        return results

    def _ingest_chunk(self, location: dict[str, Any], source: dict[str, Any], start: date, end: date) -> dict[str, Any]:
        lat, lon = float(location["requested_latitude"]), float(location["requested_longitude"])
        params = request_params(lat, lon, start, end)
        lower, upper = shanghai_period_bounds(start, end)
        batch = self.repository.create_batch({
            "weather_location_id": location["id"], "source_id": source["id"],
            "start_date": start.isoformat(), "end_date": end.isoformat(), "status": "running",
            "expected_hours": int((upper - lower).total_seconds() // 3600),
            "requested_grid_latitude": lat, "requested_grid_longitude": lon,
            "request_params": params, "started_at": utc_iso(datetime.now(timezone.utc)),
        })
        try:
            parsed, attempts = self.client.fetch(lat, lon, start, end)
            rows = [{**row, "weather_location_id": location["id"], "source_id": source["id"],
                     "batch_id": batch["id"], "ingested_at": utc_iso(datetime.now(timezone.utc))}
                    for row in parsed.rows]
            upserted = self.repository.upsert_hourly(rows)
            persisted = self.repository.hourly_rows(location["id"], source["id"], lower, upper)
            distance = grid_distance_km(lat, lon, parsed.grid_latitude, parsed.grid_longitude)
            quality = evaluate_quality(persisted, lower, upper, duplicate_hours=parsed.duplicate_hours,
                                       grid_distance_km=distance, grid_warning_km=self.grid_warning_km)
            quality["details"].update({"requested_latitude": lat, "requested_longitude": lon,
                                       "response_grid_latitude": parsed.grid_latitude,
                                       "response_grid_longitude": parsed.grid_longitude,
                                       "model": "era5", "timezone": parsed.response_timezone,
                                       "hourly_units": parsed.hourly_units})
            self.repository.insert_quality({**quality, "weather_location_id": location["id"],
                                            "source_id": source["id"], "batch_id": batch["id"]})
            status = "succeeded" if quality["status"] == "pass" else "partial"
            self.repository.update_batch(batch["id"], {
                "status": status, "received_hours": len(parsed.rows), "upserted_rows": upserted,
                "null_rh_rows": quality["null_rh_hours"], "missing_hours": quality["missing_hours"],
                "duplicate_hours": parsed.duplicate_hours, "response_grid_latitude": parsed.grid_latitude,
                "response_grid_longitude": parsed.grid_longitude, "response_elevation_m": parsed.grid_elevation_m,
                "response_timezone": parsed.response_timezone,
                "response_utc_offset_seconds": parsed.response_utc_offset_seconds,
                "hourly_units": parsed.hourly_units, "response_sha256": parsed.response_sha256,
                "attempts": attempts, "finished_at": utc_iso(datetime.now(timezone.utc)),
                "error_summary": None if status == "succeeded" else f"quality status: {quality['status']}",
            })
            result = {"port_code": location["port"]["port_code"], "start_date": start.isoformat(),
                      "end_date": end.isoformat(), "status": status, "batch_id": batch["id"],
                      "quality": quality, "grid_location": {"latitude": parsed.grid_latitude,
                                                            "longitude": parsed.grid_longitude,
                                                            "elevation_m": parsed.grid_elevation_m}}
            logger.info("weather_batch %s %s %s status=%s received=%s", result["port_code"], start, end, status, len(parsed.rows))
            return result
        except Exception as exc:
            logger.warning("weather_batch_failed port=%s start=%s end=%s reason=%s", location["port"]["port_code"], start, end, type(exc).__name__)
            # Keep the failure resumable without persisting request URLs or credentials.
            self.repository.update_batch(batch["id"], {
                "status": "failed", "attempts": self.client.retries,
                "error_summary": f"{type(exc).__name__}: {str(exc)[:180]}" if isinstance(exc, ValueError) else type(exc).__name__,
                "finished_at": utc_iso(datetime.now(timezone.utc)),
            })
            return {"port_code": location["port"]["port_code"], "start_date": start.isoformat(),
                    "end_date": end.isoformat(), "status": "failed", "batch_id": batch["id"],
                    "error": type(exc).__name__}

    def retry_failed(self) -> list[dict[str, Any]]:
        batches = (self.repository.db.table("weather_ingestion_batches").select("weather_location_id,start_date,end_date,status")
                   .in_("status", ["failed", "partial"]).order("created_at").execute().data or [])
        by_location = {item["id"]: item for item in self.repository.locations(verified_only=True)}
        seen: set[tuple[str, str, str]] = set()
        results = []
        for batch in batches:
            key = (batch["weather_location_id"], batch["start_date"], batch["end_date"])
            if key in seen or key[0] not in by_location:
                continue
            seen.add(key)
            location = by_location[key[0]]
            results.extend(self.backfill(location["port"]["port_code"], date.fromisoformat(key[1]), date.fromisoformat(key[2])))
        return results

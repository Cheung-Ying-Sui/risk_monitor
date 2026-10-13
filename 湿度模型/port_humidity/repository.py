"""Service-role-only persistence and bounded weather reads."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .open_meteo import DEFAULT_ENDPOINT
from .time_utils import shanghai_period_bounds, utc_iso, shanghai_iso


class WeatherRepository:
    def __init__(self, client: Any | None = None):
        if client is None:
            from risk_monitor.supabase_client import supabase
            client = supabase
        self.db = client

    def seed(self, seed_path: Path) -> dict[str, int]:
        ports = json.loads(seed_path.read_text(encoding="utf-8"))
        endpoint = DEFAULT_ENDPOINT
        source = {
            "provider": "open_meteo", "dataset": "era5", "api_endpoint": endpoint,
            "model_options": {"models": "era5", "cell_selection": "nearest", "timezone": "Asia/Shanghai"},
            "documentation_url": "https://open-meteo.com/en/docs/historical-weather-api",
        }
        self.db.table("weather_data_sources").upsert(source, on_conflict="provider,dataset,api_endpoint").execute()
        created_locations = 0
        for seed in ports:
            port = self.db.table("weather_ports").upsert({
                "port_code": seed["port_code"], "name_zh": seed["name_zh"],
                "region_zh": seed["region_zh"], "unlocode": seed.get("unlocode"),
                "notes": "试点名单；港口代码为内部暂定代码，不是 UN/LOCODE。",
            }, on_conflict="port_code").execute().data[0]
            existing = self.db.table("port_weather_locations").select("id").eq("port_id", port["id"]).limit(1).execute().data
            if not existing:
                self.db.table("port_weather_locations").insert({
                    "port_id": port["id"], "name": seed["location_name"],
                    "verification_status": "pending_verification", "is_primary": False,
                    "location_description": "待确认具体码头/泊位；导航港口中心点不得用作气象分析点。",
                }).execute()
                created_locations += 1
        return {"ports": len(ports), "new_pending_locations": created_locations}

    def source(self) -> dict[str, Any]:
        endpoint = DEFAULT_ENDPOINT
        rows = (self.db.table("weather_data_sources").select("*").eq("provider", "open_meteo")
                .eq("dataset", "era5").eq("api_endpoint", endpoint).limit(1).execute().data)
        if not rows:
            raise ValueError("ERA5 weather source is not seeded; run seed first")
        return rows[0]

    def locations(self, port_code: str | None = None, *, verified_only: bool = False) -> list[dict[str, Any]]:
        query = self.db.table("weather_ports").select("id,port_code,name_zh,region_zh,unlocode").order("port_code")
        if port_code:
            query = query.eq("port_code", port_code)
        ports = query.execute().data or []
        result = []
        for port in ports:
            location_query = self.db.table("port_weather_locations").select("*").eq("port_id", port["id"]).order("created_at")
            if verified_only:
                location_query = location_query.in_("verification_status", ["verified", "approximate"]).eq("is_primary", True)
            for location in location_query.execute().data or []:
                result.append({**location, "port": port})
        return result

    def primary_location(self, port_code: str) -> dict[str, Any] | None:
        locations = self.locations(port_code, verified_only=True)
        return locations[0] if locations else None

    def set_approximate_location(self, port_code: str, *, latitude: float, longitude: float,
                                 name: str, coordinate_source: str, description: str) -> dict[str, Any]:
        """Promote an existing empty placeholder; never change a point that owns hourly data."""
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("analysis-point coordinates are invalid")
        locations = self.locations(port_code)
        if not locations:
            raise ValueError("unknown pilot port; run seed first")
        existing = self.primary_location(port_code)
        if existing:
            if (existing["verification_status"] == "approximate"
                    and float(existing["requested_latitude"]) == latitude
                    and float(existing["requested_longitude"]) == longitude):
                return existing
            raise ValueError("an active location already exists; create a new version before changing coordinates")
        placeholder = next((row for row in locations if row["verification_status"] == "pending_verification"
                            and row.get("requested_latitude") is None), None)
        if not placeholder:
            raise ValueError("no empty placeholder location is available")
        values = {"name": name, "requested_latitude": latitude, "requested_longitude": longitude,
                  "coordinate_system": "WGS84", "coordinate_source": coordinate_source,
                  "location_description": description, "verification_status": "approximate",
                  "is_primary": True, "updated_at": datetime.now().astimezone().isoformat()}
        return (self.db.table("port_weather_locations").update(values)
                .eq("id", placeholder["id"]).execute().data or [])[0]

    def replace_location(self, port_code: str, *, latitude: float, longitude: float,
                         name: str, coordinate_source: str, description: str,
                         verified: bool = False) -> dict[str, Any]:
        """Create a new point ID, preserving all hourly data attached to the old point."""
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("analysis-point coordinates are invalid")
        if not all(value.strip() for value in (name, coordinate_source, description)):
            raise ValueError("name, coordinate source and description are required")
        old = self.primary_location(port_code)
        if not old:
            raise ValueError("no primary analysis point to replace")
        new = self.db.table("port_weather_locations").insert({
            "port_id": old["port_id"], "name": name.strip(),
            "requested_latitude": latitude, "requested_longitude": longitude,
            "coordinate_system": "WGS84", "coordinate_source": coordinate_source.strip(),
            "location_description": description.strip(),
            "verification_status": "verified" if verified else "approximate",
            "verified_at": datetime.now().astimezone().isoformat() if verified else None,
            "is_primary": False,
        }).execute().data[0]
        try:
            self.db.table("port_weather_locations").update({"is_primary": False}).eq("id", old["id"]).execute()
            return self.db.table("port_weather_locations").update({"is_primary": True}).eq("id", new["id"]).execute().data[0]
        except Exception:
            # Preserve the previous current point if activating the new one fails.
            self.db.table("port_weather_locations").update({"is_primary": True}).eq("id", old["id"]).execute()
            raise

    def verify_location(self, port_code: str, location_id: str, *, name: str, latitude: float, longitude: float,
                        coordinate_source: str, location_description: str, verified_at: str) -> dict[str, Any]:
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("terminal analysis-point coordinates are invalid")
        if not name.strip() or not coordinate_source.strip() or not location_description.strip():
            raise ValueError("analysis-point name, coordinate evidence and terminal description are required")
        port_rows = self.db.table("weather_ports").select("id").eq("port_code", port_code).limit(1).execute().data
        if not port_rows:
            raise ValueError("unknown pilot port")
        if self.db.table("port_weather_hourly").select("id", count="exact").eq("weather_location_id", location_id).limit(1).execute().count:
            raise ValueError("this location has historical data; register a new location version instead of overwriting coordinates")
        rows = (self.db.table("port_weather_locations").update({
            "name": name.strip(),
            "requested_latitude": latitude, "requested_longitude": longitude,
            "coordinate_source": coordinate_source.strip(), "location_description": location_description.strip(),
            "verification_status": "verified", "verified_at": verified_at, "is_primary": True,
            "updated_at": verified_at,
        }).eq("id", location_id).eq("port_id", port_rows[0]["id"]).execute().data)
        if not rows:
            raise ValueError("analysis point not found for this port")
        return rows[0]

    def latest_batch(self, location_id: str, source_id: str, start: date, end: date, *, status: str | None = None) -> dict[str, Any] | None:
        query = (self.db.table("weather_ingestion_batches").select("*")
                 .eq("weather_location_id", location_id).eq("source_id", source_id)
                 .eq("start_date", start.isoformat()).eq("end_date", end.isoformat()))
        if status:
            query = query.eq("status", status)
        rows = query.order("created_at", desc=True).limit(1).execute().data
        return rows[0] if rows else None

    def create_batch(self, data: dict[str, Any]) -> dict[str, Any]:
        return self.db.table("weather_ingestion_batches").insert(data).execute().data[0]

    def update_batch(self, batch_id: str, data: dict[str, Any]) -> None:
        self.db.table("weather_ingestion_batches").update(data).eq("id", batch_id).execute()

    def upsert_hourly(self, rows: list[dict[str, Any]]) -> int:
        for offset in range(0, len(rows), 500):
            chunk = rows[offset:offset + 500]
            self.db.table("port_weather_hourly").upsert(
                chunk, on_conflict="weather_location_id,source_id,observed_at_utc"
            ).execute()
        return len(rows)

    def hourly_rows(self, location_id: str, source_id: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = (self.db.table("port_weather_hourly").select("observed_at_utc,relative_humidity_pct,temperature_2m_c,dew_point_2m_c,precipitation_mm")
                    .eq("weather_location_id", location_id).eq("source_id", source_id)
                    .gte("observed_at_utc", utc_iso(start)).lt("observed_at_utc", utc_iso(end))
                    .order("observed_at_utc").range(offset, offset + 999).execute().data or [])
            result.extend(page)
            if len(page) < 1000:
                return result
            offset += 1000

    def profile_rows(self, location_id: str, source_id: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """Bounded server-side read; never expose the raw decade to the browser."""
        result: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = (self.db.table("port_weather_hourly")
                    .select("observed_at_utc,relative_humidity_pct,grid_latitude,grid_longitude")
                    .eq("weather_location_id", location_id).eq("source_id", source_id)
                    .gte("observed_at_utc", utc_iso(start)).lt("observed_at_utc", utc_iso(end))
                    .order("observed_at_utc").range(offset, offset + 999).execute().data or [])
            result.extend(page)
            if len(page) < 1000:
                return result
            offset += 1000

    def profile_revision(self, location_id: str, source_id: str) -> dict[str, Any] | None:
        rows = (self.db.table("port_weather_hourly")
                .select("ingested_at,grid_latitude,grid_longitude")
                .eq("weather_location_id", location_id).eq("source_id", source_id)
                .order("ingested_at", desc=True).limit(1).execute().data or [])
        return rows[0] if rows else None

    def chart_aggregates(self, location_id: str, source_id: str, grid: tuple[float, float],
                         month: int, threshold: float) -> list[dict[str, Any]]:
        return (self.db.rpc("port_humidity_chart_aggregates", {
            "p_location_id": location_id, "p_source_id": source_id,
            "p_grid_latitude": grid[0], "p_grid_longitude": grid[1],
            "p_month": month, "p_threshold": threshold,
        }).execute().data or [])

    def insert_quality(self, data: dict[str, Any]) -> None:
        self.db.table("weather_data_quality_reports").insert(data).execute()

    def list_batches(self, *, port_code: str | None = None, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        query = self.db.table("weather_ingestion_batches").select("*")
        if port_code:
            location_ids = [row["id"] for row in self.locations(port_code)]
            if not location_ids:
                return []
            query = query.in_("weather_location_id", location_ids)
        if status:
            query = query.eq("status", status)
        return query.order("created_at", desc=True).limit(min(limit, 500)).execute().data or []

    def count_hourly(self, location_id: str, source_id: str, start: datetime, end: datetime, *, null_rh: bool = False) -> int:
        query = (self.db.table("port_weather_hourly").select("id", count="exact")
                 .eq("weather_location_id", location_id).eq("source_id", source_id)
                 .gte("observed_at_utc", utc_iso(start)).lt("observed_at_utc", utc_iso(end)))
        if null_rh:
            query = query.is_("relative_humidity_pct", "null")
        return query.limit(1).execute().count or 0

    def list_weather_ports(self) -> list[dict[str, Any]]:
        source = self.source()
        result = []
        for location in self.locations():
            location_id = location["id"]
            first = (self.db.table("port_weather_hourly").select("observed_at_utc,grid_latitude,grid_longitude")
                     .eq("weather_location_id", location_id).eq("source_id", source["id"])
                     .order("observed_at_utc").limit(1).execute().data or [])
            last = (self.db.table("port_weather_hourly").select("observed_at_utc,grid_latitude,grid_longitude")
                    .eq("weather_location_id", location_id).eq("source_id", source["id"])
                    .order("observed_at_utc", desc=True).limit(1).execute().data or [])
            quality = (self.db.table("weather_data_quality_reports").select("status,generated_at")
                       .eq("weather_location_id", location_id).eq("source_id", source["id"])
                       .order("generated_at", desc=True).limit(1).execute().data or [])
            result.append({
                "port": location["port"], "analysis_location": {key: value for key, value in location.items() if key != "port"},
                "coverage_start_utc": first[0]["observed_at_utc"] if first else None,
                "coverage_end_utc": last[0]["observed_at_utc"] if last else None,
                "grid_location": {"latitude": last[0]["grid_latitude"], "longitude": last[0]["grid_longitude"]} if last else None,
                "data_quality_status": quality[0]["status"] if quality else "not_collected",
                "dataset": "ERA5", "source": "Open-Meteo", "timezone": "Asia/Shanghai",
            })
        return result

    def get_hourly_weather(self, port_code: str, start: datetime, end: datetime, *, page: int = 1, limit: int = 500) -> dict[str, Any]:
        if page < 1 or not 1 <= limit <= 1000 or end <= start:
            raise ValueError("invalid page, limit or UTC interval")
        location = self.primary_location(port_code)
        if not location:
            return {"status": "no_verified_primary_location", "rows": [], "total": 0, "port_code": port_code,
                    "dataset": "ERA5", "source": "Open-Meteo", "analysis_location": None,
                    "grid_location": None, "timezone": "UTC", "local_timezone": "Asia/Shanghai",
                    "units": {"relative_humidity_pct": "%", "temperature_2m_c": "°C", "dew_point_2m_c": "°C", "precipitation_mm": "mm"},
                    "data_quality_status": "not_collected", "page": page, "limit": limit}
        source = self.source()
        query = (self.db.table("port_weather_hourly").select("observed_at_utc,relative_humidity_pct,temperature_2m_c,dew_point_2m_c,precipitation_mm,grid_latitude,grid_longitude,grid_elevation_m", count="exact")
                 .eq("weather_location_id", location["id"]).eq("source_id", source["id"])
                 .gte("observed_at_utc", utc_iso(start)).lt("observed_at_utc", utc_iso(end))
                 .order("observed_at_utc").range((page - 1) * limit, page * limit - 1).execute())
        rows = [{**row, "observed_at_shanghai": shanghai_iso(row["observed_at_utc"])} for row in query.data or []]
        quality = (self.db.table("weather_data_quality_reports").select("status")
                   .eq("weather_location_id", location["id"]).eq("source_id", source["id"])
                   .lte("period_start_utc", utc_iso(start)).gte("period_end_utc", utc_iso(end))
                   .order("generated_at", desc=True).limit(1).execute().data or [])
        return {
            "status": "ok" if query.count else "not_collected", "port_code": port_code,
            "dataset": "ERA5", "source": "Open-Meteo", "analysis_location": location,
            "grid_location": {"latitude": rows[0]["grid_latitude"], "longitude": rows[0]["grid_longitude"], "elevation_m": rows[0]["grid_elevation_m"]} if rows else None,
            "timezone": "UTC", "local_timezone": "Asia/Shanghai",
            "units": {"relative_humidity_pct": "%", "temperature_2m_c": "°C", "dew_point_2m_c": "°C", "precipitation_mm": "mm"},
            "data_quality_status": quality[0]["status"] if quality else "not_assessed",
            "page": page, "limit": limit, "total": query.count or 0, "rows": rows,
        }

    def get_weather_coverage(self, port_code: str, start_year: int = 2016, end_year: int = 2025) -> dict[str, Any]:
        location = self.primary_location(port_code)
        if not location:
            return {"status": "no_verified_primary_location", "port_code": port_code, "years": [],
                    "dataset": "ERA5", "source": "Open-Meteo", "analysis_location": None,
                    "grid_location": None, "timezone": "UTC", "local_timezone": "Asia/Shanghai",
                    "units": {"relative_humidity_pct": "%", "temperature_2m_c": "°C", "dew_point_2m_c": "°C", "precipitation_mm": "mm"},
                    "data_quality_status": "not_collected"}
        source = self.source()
        latest = (self.db.table("port_weather_hourly").select("grid_latitude,grid_longitude,grid_elevation_m")
                  .eq("weather_location_id", location["id"]).eq("source_id", source["id"])
                  .order("observed_at_utc", desc=True).limit(1).execute().data or [])
        years = []
        for year in range(start_year, end_year + 1):
            start, end = shanghai_period_bounds(date(year, 1, 1), date(year, 12, 31))
            expected = int((end - start).total_seconds() // 3600)
            actual = self.count_hourly(location["id"], source["id"], start, end)
            null_rh = self.count_hourly(location["id"], source["id"], start, end, null_rh=True)
            ratio = actual / expected
            rh_ratio = (actual - null_rh) / expected
            years.append({"year": year, "expected_hours": expected, "actual_distinct_hours": actual,
                          "missing_hours": max(0, expected - actual), "null_rh_hours": null_rh,
                          "completeness_ratio": round(ratio, 6), "rh_valid_ratio": round(rh_ratio, 6),
                          "data_quality_status": "pass" if ratio >= .995 and rh_ratio >= .995 else "fail" if min(ratio, rh_ratio) < .95 else "warn"})
        not_collected = all(row["actual_distinct_hours"] == 0 for row in years)
        return {"status": "not_collected" if not_collected else "ok", "port_code": port_code, "dataset": "ERA5", "source": "Open-Meteo",
                "analysis_location": location, "grid_location": latest[0] if latest else None,
                "timezone": "UTC", "local_timezone": "Asia/Shanghai",
                "units": {"relative_humidity_pct": "%", "temperature_2m_c": "°C", "dew_point_2m_c": "°C", "precipitation_mm": "mm"},
                "data_quality_status": "not_collected" if not_collected else "fail" if any(row["data_quality_status"] == "fail" for row in years)
                else "warn" if any(row["data_quality_status"] == "warn" for row in years) else "pass",
                "years": years}

"""Strict Open-Meteo ERA5 monthly response client."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable
from urllib.parse import urlsplit

import requests

from .time_utils import SHANGHAI, shanghai_period_bounds, utc_iso

HOURLY = ("relative_humidity_2m", "temperature_2m", "dew_point_2m", "precipitation")
EXPECTED_UNITS = {"time": "iso8601", "relative_humidity_2m": "%", "temperature_2m": "°C", "dew_point_2m": "°C", "precipitation": "mm"}
DEFAULT_ENDPOINT = "https://archive-api.open-meteo.com/v1/archive"


class WeatherSourceError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedWeather:
    rows: list[dict[str, Any]]
    duplicate_hours: int
    grid_latitude: float
    grid_longitude: float
    grid_elevation_m: float | None
    hourly_units: dict[str, str]
    response_timezone: str
    response_utc_offset_seconds: int
    response_sha256: str


def request_params(latitude: float, longitude: float, start: date, end: date) -> dict[str, Any]:
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("analysis-point coordinates are invalid")
    return {
        "latitude": latitude, "longitude": longitude,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "hourly": ",".join(HOURLY), "models": "era5", "timezone": "Asia/Shanghai",
        "cell_selection": "nearest", "temperature_unit": "celsius",
        "precipitation_unit": "mm",
    }


def _number(value: Any, field: str, *, minimum: float | None = None, maximum: float | None = None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WeatherSourceError(f"{field} contains a non-numeric value")
    result = float(value)
    if not math.isfinite(result) or (minimum is not None and result < minimum) or (maximum is not None and result > maximum):
        raise WeatherSourceError(f"{field} contains an invalid value")
    return result


def parse_response(payload: dict[str, Any], start: date, end: date) -> ParsedWeather:
    if not isinstance(payload, dict) or payload.get("error"):
        raise WeatherSourceError("Open-Meteo returned an error response")
    if payload.get("timezone") != "Asia/Shanghai" or payload.get("utc_offset_seconds") != 28800:
        raise WeatherSourceError("Open-Meteo response is not Asia/Shanghai (+08:00)")
    units = payload.get("hourly_units")
    if not isinstance(units, dict) or any(units.get(key) != value for key, value in EXPECTED_UNITS.items()):
        raise WeatherSourceError("Open-Meteo response units do not match the expected units")
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list) or not hourly["time"]:
        raise WeatherSourceError("Open-Meteo response has no hourly timestamps")
    times = hourly["time"]
    for field in HOURLY:
        if not isinstance(hourly.get(field), list) or len(hourly[field]) != len(times):
            raise WeatherSourceError(f"Open-Meteo hourly array {field} is missing or misaligned")
    grid_lat = _number(payload.get("latitude"), "grid latitude", minimum=-90, maximum=90)
    grid_lon = _number(payload.get("longitude"), "grid longitude", minimum=-180, maximum=180)
    if grid_lat is None or grid_lon is None:
        raise WeatherSourceError("Open-Meteo response has no grid coordinates")
    elevation = _number(payload.get("elevation"), "grid elevation")
    lower, upper = shanghai_period_bounds(start, end)
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    duplicates = 0
    for index, raw_time in enumerate(times):
        if not isinstance(raw_time, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:00", raw_time):
            raise WeatherSourceError("Open-Meteo hourly timestamp must be a Shanghai whole-hour string")
        try:
            observed = datetime.fromisoformat(raw_time).replace(tzinfo=SHANGHAI).astimezone(timezone.utc)
        except ValueError as exc:
            raise WeatherSourceError("Open-Meteo hourly timestamp is malformed") from exc
        if observed.minute or observed.second or observed.microsecond or not lower <= observed < upper:
            raise WeatherSourceError("Open-Meteo hourly timestamp is outside the Shanghai date range or not an exact hour")
        iso = utc_iso(observed)
        if iso in seen:
            duplicates += 1
            continue
        seen.add(iso)
        rows.append({
            "observed_at_utc": iso,
            "relative_humidity_pct": _number(hourly["relative_humidity_2m"][index], "relative humidity", minimum=0, maximum=100),
            "temperature_2m_c": _number(hourly["temperature_2m"][index], "temperature"),
            "dew_point_2m_c": _number(hourly["dew_point_2m"][index], "dew point"),
            "precipitation_mm": _number(hourly["precipitation"][index], "precipitation", minimum=0),
            "grid_latitude": grid_lat, "grid_longitude": grid_lon, "grid_elevation_m": elevation,
        })
    rows.sort(key=lambda row: row["observed_at_utc"])
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    return ParsedWeather(rows, duplicates, grid_lat, grid_lon, elevation, dict(units), "Asia/Shanghai", 28800, digest)


class OpenMeteoClient:
    def __init__(self, endpoint: str = DEFAULT_ENDPOINT, timeout: float = 30, retries: int = 3,
                 interval: float = 1, session: requests.Session | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        endpoint_parts = urlsplit(endpoint)
        if endpoint_parts.scheme != "https" or not endpoint_parts.hostname or endpoint_parts.query or endpoint_parts.username:
            raise ValueError("Open-Meteo endpoint must be an HTTPS URL without embedded credentials or query parameters")
        if retries < 1 or timeout <= 0:
            raise ValueError("Open-Meteo retries and timeout must be positive")
        self.endpoint = endpoint
        self.timeout = timeout
        self.retries = retries
        self.interval = interval
        self.session = session or requests.Session()
        self.sleep = sleep
        self.api_key = None  # Free non-commercial archive endpoint needs no key.

    def fetch(self, latitude: float, longitude: float, start: date, end: date) -> tuple[ParsedWeather, int]:
        params = request_params(latitude, longitude, start, end)
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            if attempt > 1:
                self.sleep(min(30, 2 ** (attempt - 2)) + self.interval)
            response = None
            try:
                response = self.session.get(self.endpoint, params={**params, **({"apikey": self.api_key} if self.api_key else {})}, timeout=self.timeout,
                                            headers={"Accept": "application/json", "User-Agent": "RiskMonitor-PortHumidity/0.1"})
                if response.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"Open-Meteo HTTP {response.status_code}")
                response.raise_for_status()
                return parse_response(response.json(), start, end), attempt
            except (requests.Timeout, requests.ConnectionError, requests.HTTPError, ValueError) as exc:
                last_error = exc
                if isinstance(exc, WeatherSourceError) or (isinstance(exc, requests.HTTPError) and response is not None and response.status_code not in (429, 500, 502, 503, 504)):
                    break
        if isinstance(last_error, requests.Timeout):
            reason = "timeout"
        elif isinstance(last_error, requests.ConnectionError):
            reason = "connection error"
        elif isinstance(last_error, requests.HTTPError):
            reason = f"HTTP {response.status_code}" if response is not None else "HTTP error"
        else:
            reason = str(last_error)[:120] if isinstance(last_error, WeatherSourceError) else "invalid JSON"
        raise WeatherSourceError(f"Open-Meteo fetch failed after {attempt} attempt(s): {reason}") from last_error

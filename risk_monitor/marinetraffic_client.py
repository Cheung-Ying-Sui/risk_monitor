"""Licensed MarineTraffic vessel identity and position lookups by IMO."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import requests

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
except ImportError:
    pass


class MarineTrafficLookupError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(os.getenv("MARINETRAFFIC_API_KEY", "").strip())


def _request(endpoint: str, imo: str, **params: Any) -> list[dict[str, Any]]:
    key = os.getenv("MARINETRAFFIC_API_KEY", "").strip()
    if not key:
        raise MarineTrafficLookupError("MARINETRAFFIC_API_KEY is not configured")
    if not re.fullmatch(r"\d{7}", imo):
        raise MarineTrafficLookupError("Invalid IMO")
    try:
        response = requests.get(
            f"https://services.marinetraffic.com/api/{endpoint}/{key}",
            params={"imo": imo, **params},
            timeout=(5, 15),
        )
        response.raise_for_status()
        body = response.json()
    except (requests.RequestException, ValueError):
        # The API key is part of the request URL; never chain/log raw exceptions.
        raise MarineTrafficLookupError("MarineTraffic request failed") from None
    if not isinstance(body, list):
        raise MarineTrafficLookupError("MarineTraffic returned an unexpected response")
    return [row for row in body if isinstance(row, dict)]


def search_vessel_by_imo(imo: str) -> dict[str, Any] | None:
    rows = _request("shipsearch", imo, protocol="json")
    matches = [
        row for row in rows
        if str(row.get("IMO") or "").strip() == imo
        and re.fullmatch(r"\d{9}", str(row.get("MMSI") or "").strip())
    ]
    mmsis = {str(row["MMSI"]).strip() for row in matches}
    if len(mmsis) > 1:
        raise MarineTrafficLookupError("MarineTraffic returned multiple MMSIs for this IMO")
    if not matches:
        return None
    row = matches[0]
    return {
        "source": "marinetraffic",
        "imo": imo,
        "mmsi": str(row["MMSI"]).strip(),
        "name": row.get("SHIPNAME"),
        "ship_type": row.get("TYPE_NAME"),
        "flag_state": row.get("FLAG"),
        "callsign": row.get("CALLSIGN"),
    }


def fetch_position_by_imo(imo: str, mmsi: str) -> dict[str, Any] | None:
    rows = _request("exportvessel", imo, v=6, timespan=1440, protocol="jsono")
    matches = [
        row for row in rows
        if str(row.get("IMO") or "").strip() == imo
        and str(row.get("MMSI") or "").strip() == mmsi
        and row.get("LAT") not in (None, "")
        and row.get("LON") not in (None, "")
        and row.get("TIMESTAMP")
    ]
    if not matches:
        return None
    row = max(matches, key=lambda item: str(item["TIMESTAMP"]))
    try:
        speed = float(row["SPEED"]) / 10 if row.get("SPEED") not in (None, "") else None
    except (TypeError, ValueError):
        speed = None
    return {
        "lat": row["LAT"], "lon": row["LON"], "speed": speed,
        "course": row.get("COURSE"), "heading": row.get("HEADING"),
        "navigational_status": row.get("STATUS"),
        "destination": row.get("DESTINATION"),
        "last_position_UTC": row["TIMESTAMP"],
    }

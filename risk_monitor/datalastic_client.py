"""Optional licensed AIS lookup by IMO; credentials stay on the server."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
except ImportError:
    pass


class DatalasticLookupError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(os.getenv("DATALASTIC_API_KEY", "").strip())


def fetch_vessel_by_imo(imo: str) -> dict[str, Any]:
    api_key = os.getenv("DATALASTIC_API_KEY", "").strip()
    if not api_key:
        raise DatalasticLookupError("DATALASTIC_API_KEY is not configured")
    try:
        response = requests.get(
            "https://api.datalastic.com/api/v0/vessel",
            params={"imo": imo},
            headers={"x-api-key": api_key, "Accept": "application/json"},
            timeout=(5, 15),
        )
        response.raise_for_status()
        body = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise DatalasticLookupError("AIS provider request failed") from exc
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        raise DatalasticLookupError("AIS provider returned no vessel data")
    return data

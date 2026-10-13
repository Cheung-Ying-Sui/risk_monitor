import json
import os
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

try:
    from dotenv import load_dotenv

    load_dotenv()
    load_dotenv(
        Path(__file__).resolve().parents[1] / "制裁筛查模块" / ".env",
        override=False,
    )
except ImportError:
    pass


class ChinaportsClientError(RuntimeError):
    pass


CHINAPORTS_SHIP_INFO_URL = "https://ship.chinaports.com/ShipInit/shipInfo"


def _build_headers():
    chinaports_cookie = os.getenv("CHINAPORTS_COOKIE")
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://ship.chinaports.com",
        "Referer": "https://ship.chinaports.com/",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/18.5 Safari/605.1.15"
        ),
        "X-Requested-With": "XMLHttpRequest",
    }

    if chinaports_cookie:
        headers["Cookie"] = chinaports_cookie

    return headers


def _build_payload(mmsi_id):
    return {
        "userid": mmsi_id,
        "source": "0",
        "num": str(int(time.time() * 1000)),
        "encode": "false",
        "lang": "ZH",
        "zone": "-480",
    }


def _parse_json_response(response_text):
    try:
        return json.loads(response_text)
    except ValueError as exc:
        raise ChinaportsClientError(
            "Chinaports returned a non-JSON response."
        ) from exc


def _fetch_ship_info_with_requests(mmsi_id):
    headers = _build_headers()
    payload = _build_payload(mmsi_id)

    try:
        response = requests.post(
            CHINAPORTS_SHIP_INFO_URL,
            headers=headers,
            data=payload,
            timeout=(
                5,
                15,
            ),
        )
        if response.status_code == 200:
            return _parse_json_response(response.text)

        raise ChinaportsClientError(
            "Chinaports request failed "
            f"with status_code={response.status_code}."
        )
    except requests.RequestException as exc:
        raise ChinaportsClientError(
            f"Chinaports request error: {exc}"
        ) from exc


def _fetch_ship_info_with_curl(mmsi_id):
    headers = _build_headers()
    payload = _build_payload(mmsi_id)
    command = [
        "curl",
        "-sS",
        "--fail-with-body",
        "--connect-timeout",
        "15",
        "--max-time",
        "30",
        CHINAPORTS_SHIP_INFO_URL,
    ]

    for key, value in headers.items():
        command.extend(
            [
                "-H",
                f"{key}: {value}",
            ]
        )

    command.extend(
        [
            "--data",
            urlencode(payload),
        ]
    )

    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=35,
        )
    except FileNotFoundError as exc:
        raise ChinaportsClientError(
            "curl is not available for Chinaports fallback."
        ) from exc
    except subprocess.CalledProcessError as exc:
        error_text = (exc.stderr or exc.stdout or "").strip()
        raise ChinaportsClientError(
            f"Chinaports curl fallback failed: {error_text}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ChinaportsClientError(
            "Chinaports curl fallback timed out."
        ) from exc

    return _parse_json_response(result.stdout)


def _fetch_by_mmsi(mmsi_id):
    try:
        return _fetch_ship_info_with_requests(mmsi_id)
    except ChinaportsClientError:
        return _fetch_ship_info_with_curl(mmsi_id)


def fetch_ship_info(mmsi_id=None, *, imo=None, mmsi=None):
    """Prefer an IMO search; use MMSI directly only when IMO is absent.

    The website's shipInfo endpoint accepts MMSI. IMO must first be resolved
    through its search endpoint. Positional identifiers remain supported.
    """
    identifier = str(mmsi_id or "").strip()
    imo = str(imo or "").strip()
    mmsi = str(mmsi or "").strip()
    if identifier:
        if len(identifier) == 7 and not imo:
            imo = identifier
        elif not mmsi:
            mmsi = identifier
    if imo and not re.fullmatch(r"[0-9]{7}", imo):
        raise ChinaportsClientError("IMO must contain seven digits.")
    if mmsi and not re.fullmatch(r"[0-9]{9}", mmsi):
        raise ChinaportsClientError("MMSI must contain nine digits.")
    if not imo:
        if not mmsi:
            raise ChinaportsClientError("IMO or MMSI is required.")
        data = _fetch_by_mmsi(mmsi)
        if not isinstance(data, dict) or str(data.get("mmsi") or data.get("MMSI") or "") != mmsi:
            raise ChinaportsClientError("Chinaports returned a different MMSI.")
        return data

    try:
        response = requests.post(
            "https://ship.chinaports.com/newshipquery/search",
            headers=_build_headers(),
            data={"isall": "0", "vession": "0", "cnqp": imo, "queryParam": imo},
            timeout=(5, 15),
        )
        response.raise_for_status()
        rows = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise ChinaportsClientError("Chinaports IMO search unavailable.") from exc
    if not isinstance(rows, list):
        raise ChinaportsClientError("Chinaports IMO search returned invalid data.")
    candidates = list(dict.fromkeys(
        str(row[1]) for row in rows
        if isinstance(row, list) and len(row) >= 4
        and str(row[2]) == "3" and str(row[3]).strip() == imo
        and re.fullmatch(r"[0-9]{9}", str(row[1]))
    ))
    if mmsi:
        candidates = [mmsi] if mmsi in candidates else []
    if not candidates or len(candidates) > 5:
        raise ChinaportsClientError("Chinaports IMO search has no unambiguous matching identity.")
    matches = []
    for candidate in candidates:
        try:
            data = _fetch_by_mmsi(candidate)
        except ChinaportsClientError:
            continue
        if (isinstance(data, dict)
                and str(data.get("imo") or data.get("IMO") or "").strip() == imo
                and str(data.get("mmsi") or data.get("MMSI") or "").strip() == candidate):
            matches.append(data)
    if len(matches) != 1:
        raise ChinaportsClientError("Chinaports IMO identity could not be uniquely verified.")
    return matches[0]

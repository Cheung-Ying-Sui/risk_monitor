import os
import time

import requests

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def fetch_ship_info(mmsi_id):
    url = "https://ship.chinaports.com/ShipInit/shipInfo"
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

    payload = {
        "userid": mmsi_id,
        "source": "0",
        "num": str(int(time.time() * 1000)),
        "encode": "false",
        "lang": "ZH",
        "zone": "-480",
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            data=payload,
            timeout=30,
        )
        if response.status_code == 200:
            return response.json()

        print(
            f"Chinaports request failed for mmsi={mmsi_id}, "
            f"status_code={response.status_code}"
        )
        return None
    except Exception as exc:
        print(
            f"Chinaports request error for mmsi={mmsi_id}: {exc}"
        )
        return None

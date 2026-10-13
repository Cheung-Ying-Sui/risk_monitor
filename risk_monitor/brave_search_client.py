"""Search public web snippets for a vessel identity without scraping result pages."""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

import requests


class BraveSearchError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(os.getenv("BRAVE_SEARCH_API_KEY", "").strip())


def search_vessel_mmsi(imo: str, vessel_name: str | None = None) -> list[dict[str, str]]:
    api_key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
    if not api_key:
        raise BraveSearchError("未配置 BRAVE_SEARCH_API_KEY，无法联网检索 MMSI。")
    if not re.fullmatch(r"\d{7}", imo):
        raise BraveSearchError("联网检索需要有效的 7 位 IMO。")

    # Bound the query to the declared IMO; never fetch a model-supplied URL.
    query = f'"{imo}" MMSI'
    try:
        response = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
            params={"q": query, "count": 8, "extra_snippets": "true"},
            timeout=(5, 15),
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise BraveSearchError("网页搜索服务暂不可用，未返回 MMSI 候选。") from exc

    web: Any = payload.get("web") if isinstance(payload, dict) else None
    raw_results: Any = web.get("results") if isinstance(web, dict) else None
    if not isinstance(raw_results, list):
        return []
    results = []
    for raw in raw_results[:8]:
        if not isinstance(raw, dict):
            continue
        url = str(raw.get("url") or "")
        if urlparse(url).scheme != "https" or not urlparse(url).netloc:
            continue
        snippets = raw.get("extra_snippets") or []
        if not isinstance(snippets, list):
            snippets = []
        results.append({
            "url": url[:1000],
            "title": str(raw.get("title") or "")[:250],
            "description": str(raw.get("description") or "")[:800],
            "extra_snippets": "\n".join(str(part)[:500] for part in snippets[:5]),
        })
    return results

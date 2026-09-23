import time
from urllib.parse import urljoin, urlsplit

import requests

from .config import Settings
from .logging_utils import log
from .models import FetchedFeed, FetchedPage, utcnow

LIST_URL = "https://www.ukmto.org/recent-incidents"
# Public production endpoint used by the official RecentIncident component (2026-09-22).
FEED_URL = "https://sccd.royalnavy.mod.uk/api/ukmto/all"


class FetchError(RuntimeError):
    pass


def validate_source_url(url: str) -> None:
    parts = urlsplit(url)
    official = parts.hostname in {"ukmto.org", "www.ukmto.org"} or url == FEED_URL
    if (parts.scheme != "https" or not official
            or parts.username or parts.password or parts.port not in (None, 443)):
        raise FetchError("Only official UKMTO HTTPS URLs are permitted")


class UKMTOClient:
    def __init__(self, settings: Settings, session=None, sleep=time.sleep, clock=time.monotonic):
        self.settings = settings
        self.session = session if session is not None else requests.Session()
        self.session.headers.update({"User-Agent": settings.user_agent, "Accept": "text/html"})
        self.sleep = sleep
        self.clock = clock
        self.last_request: float | None = None

    def close(self) -> None:
        self.session.close()

    def _request(self, url: str):
        validate_source_url(url)
        for attempt in range(self.settings.retries + 1):
            if self.last_request is not None:
                delay = self.settings.request_interval - (self.clock() - self.last_request)
                if delay > 0:
                    self.sleep(delay)
            self.last_request = self.clock()
            try:
                response = self.session.get(url, timeout=self.settings.timeout, allow_redirects=False)
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt == self.settings.retries:
                    raise FetchError(f"Network request failed ({type(exc).__name__})") from exc
            else:
                if response.status_code < 500:
                    if response.status_code >= 400:
                        response.close()
                        raise FetchError(f"UKMTO returned HTTP {response.status_code}")
                    return response
                status = response.status_code
                response.close()
                if attempt == self.settings.retries:
                    raise FetchError(f"UKMTO returned HTTP {status} after retries")
            log("ukmto_request_retry", source_url=url, attempt=attempt + 1)
            self.sleep(2 ** attempt)
        raise AssertionError("unreachable")

    def _fetch_response(self, url: str):
        for _ in range(6):
            response = self._request(url)
            if response.status_code in {301, 302, 303, 307, 308}:
                target = response.headers.get("Location")
                response.close()
                if not target:
                    raise FetchError("Redirect is missing Location")
                url = urljoin(url, target)
                continue
            return url, response
        raise FetchError("Too many redirects")

    def fetch(self, url: str) -> FetchedPage:
        url, response = self._fetch_response(url)
        try:
            content_type = response.headers.get("Content-Type", "").lower()
            if "html" not in content_type:
                raise FetchError(f"Expected HTML, received {content_type or 'unknown content type'}")
            if "charset=" not in content_type:
                response.encoding = "utf-8"
            return FetchedPage(url, response.text, utcnow())
        finally:
            response.close()

    def fetch_feed(self) -> FetchedFeed:
        url, response = self._fetch_response(FEED_URL)
        try:
            if "json" not in response.headers.get("Content-Type", "").lower():
                raise FetchError("Expected JSON from the official incident feed")
            try:
                data = response.json()
            except ValueError as exc:
                raise FetchError("Invalid JSON in the official incident feed") from exc
            return FetchedFeed(url, data, utcnow())
        finally:
            response.close()

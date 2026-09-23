import logging
from typing import Callable
from urllib.parse import urldefrag

from .client import LIST_URL, UKMTOClient
from .logging_utils import error_fields, log
from .models import ParsedUKMTOIncident, RunResult, utcnow
from .parser import (extract_incident_links, feed_records, feed_source_url, has_dynamic_incidents,
                     parse_feed_incident, parse_incident)
from .repository import IncidentRepository, RepositoryError


class UKMTOService:
    def __init__(self, client: UKMTOClient, repository: IncidentRepository | None = None):
        self.client = client
        self.repository = repository

    def run(self, *, dry_run: bool = False, max_incidents: int = 100,
            on_parsed: Callable[[ParsedUKMTOIncident], None] | None = None) -> RunResult:
        if not dry_run and self.repository is None:
            raise ValueError("A repository is required unless dry_run=True")
        if max_incidents < 1:
            raise ValueError("max_incidents must be positive")
        result = RunResult()
        log("ukmto_fetch_started", dry_run=dry_run, max_incidents=max_incidents)
        try:
            listing = self.client.fetch(LIST_URL)
            dynamic = has_dynamic_incidents(listing.html)
            if dynamic:
                feed = self.client.fetch_feed()
                entries = feed_records(feed.data)[:max_incidents]
            else:
                entries = extract_incident_links(listing.html, listing.url)[:max_incidents]
            log("ukmto_list_fetched", source_url=listing.url, link_count=len(entries),
                transport="official_json" if dynamic else "html")
        except Exception as exc:
            result.list_failed = True
            result.failed_count = 1
            log("ukmto_list_failed", level=logging.ERROR, source_url=LIST_URL, **error_fields(exc))
        else:
            # Cache transport only; all durable deduplication remains in PostgreSQL.
            pages = {urldefrag(listing.url)[0]: listing}
            seen_versions = set()
            for entry in entries:
                incident = None
                source_url = LIST_URL
                try:
                    if dynamic:
                        source_url = feed_source_url(entry)
                        page = feed
                    else:
                        source_url = entry.url
                        fetch_url = urldefrag(entry.url)[0]
                        if fetch_url not in pages:
                            pages[fetch_url] = self.client.fetch(fetch_url)
                        page = pages[fetch_url]
                    result.fetched_count += 1
                    incident = parse_feed_incident(entry) if dynamic else parse_incident(page.html, entry.url, entry.title)
                    result.parsed_count += 1
                    incident.raw_payload["fetched_at"] = page.fetched_at.isoformat()
                    incident.raw_payload["resolved_url"] = page.url
                    log("ukmto_incident_parsed", source_url=source_url, external_id=incident.external_id)
                    log("ukmto_incident_metadata", level=logging.DEBUG,
                        external_id=incident.external_id, content_hash=incident.content_hash,
                        location_precision=incident.location_precision)
                    for warning in incident.raw_payload.get("warnings", []):
                        log("ukmto_parse_warning", level=logging.WARNING, warning=warning,
                            source_url=source_url, external_id=incident.external_id)
                    if on_parsed:
                        on_parsed(incident)
                    version = (incident.external_id, incident.content_hash)
                    if dry_run or version in seen_versions:
                        continue
                    action = self.repository.save(incident, page.fetched_at)
                    seen_versions.add(version)
                    setattr(result, f"{action}_count", getattr(result, f"{action}_count") + 1)
                    log(f"ukmto_incident_{action}", source_url=source_url, external_id=incident.external_id)
                except Exception as exc:
                    result.failed_count += 1
                    if isinstance(exc, RepositoryError):
                        result.database_failed_count += 1
                    log("ukmto_incident_failed", level=logging.ERROR, source_url=source_url,
                        external_id=incident.external_id if incident else None, **error_fields(exc))
        result.finished_at = utcnow()
        log("ukmto_fetch_finished", **result.payload(), exit_code=result.exit_code)
        return result

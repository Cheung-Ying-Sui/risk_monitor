from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class FetchedPage:
    url: str
    html: str
    fetched_at: datetime


@dataclass(frozen=True)
class FetchedFeed:
    url: str
    data: Any
    fetched_at: datetime


@dataclass(frozen=True)
class IncidentLink:
    url: str
    title: str | None = None


@dataclass
class ParsedUKMTOIncident:
    external_id: str
    incident_number: str | None
    incident_type: str
    title: str
    description: str
    source_url: str
    content_hash: str = ""
    incident_time: datetime | None = None
    published_at: datetime | None = None
    source_updated_at: datetime | None = None
    location_text: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    location_precision: str = "unknown"
    region: str | None = None
    vessel_type: str | None = None
    source_type: str = "unknown"
    verification_status: str = "unknown"
    casualties: str | None = None
    environmental_impact: str | None = None
    source: str = "UKMTO"
    status: str = "active"
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        return {
            key: value.isoformat() if isinstance(value, datetime) else value
            for key, value in asdict(self).items()
        }


@dataclass
class RunResult:
    started_at: datetime = field(default_factory=utcnow)
    finished_at: datetime | None = None
    fetched_count: int = 0
    parsed_count: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    failed_count: int = 0
    database_failed_count: int = 0
    list_failed: bool = False

    @property
    def exit_code(self) -> int:
        if self.list_failed:
            return 2
        if self.database_failed_count:
            return 3
        return 4 if self.failed_count else 0

    def payload(self) -> dict:
        return {
            key: value.isoformat() if isinstance(value, datetime) else value
            for key, value in asdict(self).items()
        }

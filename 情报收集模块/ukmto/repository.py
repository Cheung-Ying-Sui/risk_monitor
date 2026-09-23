from datetime import datetime
from typing import Protocol

from .models import ParsedUKMTOIncident


class RepositoryError(RuntimeError):
    pass


class IncidentRepository(Protocol):
    def save(self, incident: ParsedUKMTOIncident, observed_at: datetime) -> str: ...


class SupabaseIncidentRepository:
    def __init__(self, client):
        self.client = client

    def save(self, incident: ParsedUKMTOIncident, observed_at: datetime) -> str:
        """One transactional RPC prevents main-table/history partial writes and races."""
        try:
            result = self.client.rpc("ingest_ukmto_incident", {
                "p_incident": incident.payload(), "p_observed_at": observed_at.isoformat(),
            }).execute().data
        except Exception as exc:
            # Do not propagate SDK exception text: it may contain credentials/headers.
            raise RepositoryError(f"Supabase ingestion failed ({type(exc).__name__})") from exc
        if result not in {"inserted", "updated", "unchanged"}:
            raise RepositoryError("Unexpected response from ingest_ukmto_incident")
        return result

    def get(self, external_id: str) -> dict | None:
        response = self.client.table("ukmto_incidents").select("*").eq("source", "UKMTO").eq("external_id", external_id).limit(1).execute()
        return response.data[0] if response.data else None

    def list_incidents(self, *, from_time: datetime | None = None, to_time: datetime | None = None,
                       incident_type: str | None = None, region: str | None = None,
                       status: str | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
        """Future FastAPI adapter: time filters use published_at, inclusive bounds."""
        if not 1 <= limit <= 1000 or offset < 0:
            raise ValueError("Invalid pagination")
        if from_time and to_time and from_time > to_time:
            raise ValueError("from_time must not exceed to_time")
        query = self.client.table("ukmto_incidents").select("*").eq("source", "UKMTO")
        for column, value in (("incident_type", incident_type), ("region", region), ("status", status)):
            if value is not None:
                query = query.eq(column, value)
        if from_time:
            query = query.gte("published_at", from_time.isoformat())
        if to_time:
            query = query.lte("published_at", to_time.isoformat())
        return query.order("published_at", desc=True, nullsfirst=False).order("external_id").range(offset, offset + limit - 1).execute().data

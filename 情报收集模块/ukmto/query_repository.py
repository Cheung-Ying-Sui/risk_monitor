"""Read-only Supabase queries for the HTTP API; ingestion stays independent."""
from dataclasses import dataclass
from datetime import datetime

from .api_schemas import IncidentResponse

PUBLIC_COLUMNS = ','.join(IncidentResponse.model_fields)


@dataclass(frozen=True)
class IncidentFilters:
    from_time: datetime | None = None
    to_time: datetime | None = None
    incident_type: str | None = None
    region: str | None = None
    status: str | None = None
    limit: int = 100
    offset: int = 0


class IncidentQueryRepository:
    def __init__(self, client):
        self.client = client

    def get(self, external_id: str) -> dict | None:
        response = (self.client.table('ukmto_incidents').select(PUBLIC_COLUMNS)
                    .eq('source', 'UKMTO').eq('external_id', external_id).limit(1).execute())
        return response.data[0] if response.data else None

    def list(self, filters: IncidentFilters, *, coordinates_only: bool = False) -> tuple[list[dict], int]:
        query = self.client.table('ukmto_incidents').select(PUBLIC_COLUMNS, count='exact').eq('source', 'UKMTO')
        for column, value in [('incident_type', filters.incident_type), ('region', filters.region), ('status', filters.status)]:
            if value is not None:
                query = query.eq(column, value)
        if filters.from_time is not None:
            query = query.gte('published_at', filters.from_time.isoformat())
        if filters.to_time is not None:
            query = query.lte('published_at', filters.to_time.isoformat())
        if coordinates_only:
            # Filter before pagination/count so unmapped reports cannot consume a map page.
            query = query.gte('latitude', -90).lte('latitude', 90).gte('longitude', -180).lte('longitude', 180)
        response = (query.order('published_at', desc=True, nullsfirst=False).order('external_id')
                    .range(filters.offset, filters.offset + filters.limit - 1).execute())
        if response.count is None:
            raise RuntimeError('Supabase did not return the requested total count')
        return response.data, response.count

"""Public API schemas: never expose raw source payloads or database credentials."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

IncidentType = Literal['attack', 'suspicious_activity', 'hijack', 'advisory', 'military_interaction', 'unknown']


class IncidentResponse(BaseModel):
    external_id: str
    source: str = 'UKMTO'
    incident_number: str | None = None
    incident_type: IncidentType
    title: str | None = None
    description: str | None = None
    incident_time: datetime | None = None
    published_at: datetime | None = None
    source_updated_at: datetime | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    updated_at: datetime | None = None
    location_text: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    location_precision: str | None = None
    region: str | None = None
    vessel_type: str | None = None
    source_type: str | None = None
    verification_status: str | None = None
    casualties: str | None = None
    environmental_impact: str | None = None
    source_url: str
    status: str = 'active'


class Pagination(BaseModel):
    total: int
    limit: int
    offset: int
    has_more: bool
    next_offset: int | None = None


class IncidentListResponse(Pagination):
    items: list[IncidentResponse]


class PointGeometry(BaseModel):
    type: Literal['Point'] = 'Point'
    coordinates: tuple[float, float]


class IncidentFeature(BaseModel):
    type: Literal['Feature'] = 'Feature'
    id: str
    geometry: PointGeometry
    properties: IncidentResponse


class IncidentFeatureCollection(BaseModel):
    type: Literal['FeatureCollection'] = 'FeatureCollection'
    features: list[IncidentFeature]
    pagination: Pagination

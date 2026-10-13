from datetime import datetime

from pydantic import BaseModel, Field


class VesselResponse(BaseModel):
    id: str | None = None
    mmsi: str | None = None
    imo: str | None = None
    name: str | None = None
    ship_type: str | None = None
    flag_state: str | None = None
    callsign: str | None = None


class LatestPositionResponse(BaseModel):
    vessel_id: str | None = None
    latitude: float
    longitude: float
    sog: float | None = None
    cog: float | None = None
    heading: float | None = None
    navigation_status: str | None = None
    destination: str | None = None
    observed_at: datetime

class TrackPointResponse(LatestPositionResponse):
    id: int | None = None
    received_at: datetime | None = None


class VesselSearchResponse(VesselResponse):
    source: str
    is_persisted: bool
    is_tracked: bool
    latest_position: LatestPositionResponse | None = None


class ExternalLatestPosition(BaseModel):
    latitude: float
    longitude: float
    sog: float | None = None
    cog: float | None = None
    heading: float | None = None
    navigation_status: str | None = None
    destination: str | None = None
    observed_at: datetime


class VesselOnboardRequest(BaseModel):
    source: str = "chinaports"
    mmsi: str
    imo: str | None = None
    name: str | None = None
    callsign: str | None = None
    ship_type: str | None = None
    flag_state: str | None = None
    length_m: float | None = None
    width_m: float | None = None
    gross_tonnage: float | None = None
    latest_position: ExternalLatestPosition | None = None


class VesselOnboardResponse(VesselSearchResponse):
    warnings: list[str] = Field(default_factory=list)


class TrackingStatusUpdate(BaseModel):
    is_active: bool


class TrackingStatusResponse(BaseModel):
    vessel_id: str
    is_active: bool

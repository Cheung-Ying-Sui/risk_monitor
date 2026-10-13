from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DestinationPredictionResponse(BaseModel):
    port_id: str | None = None
    name: str | None = None
    confidence: float = Field(ge=0, le=1)


class ProjectedPositionResponse(BaseModel):
    longitude: float
    latitude: float


class RoutePredictionResponse(BaseModel):
    prediction_id: str
    version: int
    geojson: dict[str, Any]
    remaining_geojson: dict[str, Any]
    remaining_distance_nm: float = Field(ge=0)
    total_distance_nm: float = Field(gt=0)
    progress: float = Field(ge=0, le=1)
    cross_track_error_nm: float = Field(ge=0)
    cross_track_error_m: float = Field(ge=0)
    projected_position: ProjectedPositionResponse
    source: str
    status: str
    latest_ais_destination: str | None = None
    destination_matches_latest_ais: bool | None = None


class EtaPredictionResponse(BaseModel):
    estimated_arrival_at: datetime | None = None
    remaining_hours: float | None = Field(default=None, ge=0)
    estimated_speed_knots: float | None = Field(default=None, gt=0)
    speed_method: str
    speed_sample_count: int = Field(ge=0)
    speed_variability: float | None = Field(default=None, ge=0)
    confidence: float = Field(ge=0, le=1)


class PredictionQualityResponse(BaseModel):
    confidence: float = Field(ge=0, le=1)
    ais_age_seconds: float | None = Field(default=None, ge=0)
    reroute_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class NavigationPredictionResponse(BaseModel):
    status: str
    vessel_id: str
    mmsi: str
    prediction_timestamp: datetime
    based_on_observed_at: datetime
    destination: DestinationPredictionResponse
    route: RoutePredictionResponse
    eta: EtaPredictionResponse
    risk_zone_crossings: list[dict[str, Any]] = Field(default_factory=list)
    prediction_quality: PredictionQualityResponse

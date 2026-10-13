from typing import Any, Literal

from pydantic import BaseModel


class RiskZoneGeometry(BaseModel):
    type: Literal["Polygon", "MultiPolygon"]
    coordinates: list[Any]


class RiskZoneProperties(BaseModel):
    zone_id: str | None = None
    zone_version_id: str | None = None
    zone_name: str
    zone_type: str
    source: str | None = None
    source_document: str | None = None
    effective_date: str | None = None


class RiskZoneFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: RiskZoneGeometry
    properties: RiskZoneProperties


class RiskZoneFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[RiskZoneFeature]

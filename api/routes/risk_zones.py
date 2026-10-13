from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.schemas.risk_zones import (
    RiskZoneFeature,
    RiskZoneFeatureCollection,
    RiskZoneGeometry,
    RiskZoneProperties,
)


router = APIRouter(
    prefix="/api/v1/risk-zones",
    tags=["risk-zones"],
)


class RiskZoneRepository:
    def get_active_risk_zones_geojson(self) -> list[dict[str, Any]]:
        from risk_monitor.risk_repository import get_active_risk_zones_geojson

        return get_active_risk_zones_geojson()


def get_risk_zone_repository() -> RiskZoneRepository:
    return RiskZoneRepository()


def _text(value: Any, fallback: str | None = None) -> str | None:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


@router.get("", response_model=RiskZoneFeatureCollection)
def list_active_maritime_risk_zones(
    repository: RiskZoneRepository = Depends(get_risk_zone_repository),
) -> RiskZoneFeatureCollection:
    try:
        zones = repository.get_active_risk_zones_geojson()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Risk zone repository query failed.",
        ) from exc

    features: list[RiskZoneFeature] = []
    for zone in zones or []:
        if _text(zone.get("zone_type")) != "maritime":
            continue

        geometry = zone.get("geometry_geojson")
        if not isinstance(geometry, dict):
            continue
        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates")
        if geometry_type not in {"Polygon", "MultiPolygon"} or not isinstance(coordinates, list):
            continue

        features.append(
            RiskZoneFeature(
                geometry=RiskZoneGeometry(
                    type=geometry_type,
                    coordinates=coordinates,
                ),
                properties=RiskZoneProperties(
                    zone_id=_text(zone.get("zone_id")),
                    zone_version_id=_text(zone.get("zone_version_id")),
                    zone_name=_text(zone.get("zone_name"), "未命名高风险海区") or "未命名高风险海区",
                    zone_type="maritime",
                    source=_text(zone.get("source")),
                    source_document=_text(zone.get("source_document")),
                    effective_date=_text(zone.get("effective_date")),
                ),
            )
        )

    return RiskZoneFeatureCollection(features=features)

"""UKMTO read routes, mounted by the existing api.main application."""
import logging
import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values
from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Query
from fastapi.responses import JSONResponse

from .api_schemas import (IncidentFeature, IncidentFeatureCollection, IncidentListResponse,
                          IncidentResponse, IncidentType, Pagination, PointGeometry)
from .query_repository import IncidentFilters, IncidentQueryRepository

router = APIRouter(prefix='/api/v1/ukmto', tags=['ukmto'])
logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _database_client():
    # Same precedence as the collector, without modifying process-wide environment.
    module = Path(__file__).resolve().parents[1]
    config = {}
    if os.getenv('PYTHON_DOTENV_DISABLED', '').lower() not in {'1', 'true', 'yes', 'on'}:
        config.update(dotenv_values(module.parent / '.env'))
        config.update(dotenv_values(module / '.env'))
    config.update(os.environ)
    url = config.get('SUPABASE_URL')
    key = (config.get('SUPABASE_SERVICE_KEY') or config.get('SUPABASE_SERVICE_ROLE_KEY')
           or config.get('SUPABASE_SECRET_KEY'))
    if not url or not key:
        raise RuntimeError('UKMTO database configuration missing')
    from supabase import create_client
    return create_client(url, key)


def unavailable(exc: Exception) -> HTTPException:
    # Log the exception class only: SDK messages can contain headers or credentials.
    logger.error('ukmto_api_query_failed exception_type=%s', type(exc).__name__)
    return HTTPException(status_code=503, detail='UKMTO incident data is temporarily unavailable.')


def get_incident_repository() -> IncidentQueryRepository:
    try:
        return IncidentQueryRepository(_database_client())
    except Exception as exc:
        raise unavailable(exc) from None


def get_proximity_repository():
    from risk_monitor.maritime_proximity import ProximityRepository
    return ProximityRepository()


def incident_filters(
    from_time: datetime | None = Query(None, alias='from', description='Inclusive published_at lower bound; naive dates use UTC.'),
    to_time: datetime | None = Query(None, alias='to', description='Inclusive published_at upper bound; naive dates use UTC.'),
    incident_type: IncidentType | None = Query(None),
    region: str | None = Query(None, min_length=1, max_length=100),
    status: str | None = Query(None, min_length=1, max_length=64),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> IncidentFilters:
    def utc(value):
        return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc) if value else None
    from_time, to_time = utc(from_time), utc(to_time)
    if from_time and to_time and from_time > to_time:
        raise HTTPException(status_code=422, detail='from must be earlier than or equal to to.')
    return IncidentFilters(from_time, to_time, incident_type, region, status, limit, offset)


def pagination(filters: IncidentFilters, total: int, returned: int) -> Pagination:
    next_offset = filters.offset + returned
    more = returned > 0 and next_offset < total
    return Pagination(total=total, limit=filters.limit, offset=filters.offset,
                      has_more=more, next_offset=next_offset if more else None)


def read_page(repository, filters, coordinates_only=False):
    try:
        rows, total = repository.list(filters, coordinates_only=coordinates_only)
        items = [IncidentResponse.model_validate(row) for row in rows]
        return items, pagination(filters, total, len(rows))
    except Exception as exc:
        raise unavailable(exc) from None


@router.get('/incidents', response_model=IncidentListResponse)
def list_incidents(filters: IncidentFilters = Depends(incident_filters),
                   repository: IncidentQueryRepository = Depends(get_incident_repository)):
    items, page = read_page(repository, filters)
    return IncidentListResponse(items=items, **page.model_dump())


@router.get('/vessel-risk-counts')
def vessel_risk_counts(filters: IncidentFilters = Depends(incident_filters),
                       repository=Depends(get_proximity_repository),
                       incidents: IncidentQueryRepository = Depends(get_incident_repository)):
    from risk_monitor.maritime_proximity import query_counts
    try:
        return query_counts(repository, incidents, filters)
    except Exception as exc:
        raise unavailable(exc) from None


class GeoJSONResponse(JSONResponse):
    media_type = 'application/geo+json'


# Static route must be declared before /incidents/{external_id}.
@router.get('/incidents.geojson', response_model=IncidentFeatureCollection, response_class=GeoJSONResponse)
def incidents_geojson(filters: IncidentFilters = Depends(incident_filters),
                      repository: IncidentQueryRepository = Depends(get_incident_repository)):
    items, page = read_page(repository, filters, coordinates_only=True)
    features = [IncidentFeature(id=item.external_id,
                geometry=PointGeometry(coordinates=(item.longitude, item.latitude)), properties=item)
                for item in items if item.latitude is not None and item.longitude is not None]
    return IncidentFeatureCollection(features=features, pagination=page)


@router.get('/incidents/{external_id}', response_model=IncidentResponse)
def incident_detail(external_id: str = PathParam(min_length=1, max_length=200),
                    repository: IncidentQueryRepository = Depends(get_incident_repository)):
    try:
        row = repository.get(external_id)
        incident = IncidentResponse.model_validate(row) if row is not None else None
    except Exception as exc:
        raise unavailable(exc) from None
    if incident is None:
        raise HTTPException(status_code=404, detail='UKMTO incident not found.')
    return incident

"""Bounded read-only internal weather API; database credentials remain server-side."""

from datetime import date, datetime, time
from math import isfinite
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from httpx import TransportError
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/port-weather", tags=["port-weather"])


def get_weather_repository():
    from 湿度模型.port_humidity.repository import WeatherRepository
    return WeatherRepository()


def get_arrivals_repository():
    from risk_monitor.port_arrivals import PortArrivalRepository
    return PortArrivalRepository()


class PortArrival(BaseModel):
    vessel_name: str
    imo_number: str | None
    eta: datetime
    eta_source: str
    eta_scope: str
    declaration_id: str
    shipment_id: str
    discharge_port: str | None
    matched_port_codes: list[str]


class PortArrivalsResponse(BaseModel):
    port_code: str
    timezone: str
    window_start: datetime
    window_end: datetime
    eta_source: str
    arrivals: list[PortArrival]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise HTTPException(status_code=422, detail="UTC interval timestamps must include a timezone")
    return value


@router.get("/ports")
def list_weather_ports(repository: Any = Depends(get_weather_repository)):
    try:
        return repository.list_weather_ports()
    except TransportError as exc:
        raise HTTPException(status_code=503, detail="Historical weather service temporarily unavailable") from exc


@router.get("/ports/{port_code}/arrivals", response_model=PortArrivalsResponse)
def list_port_arrivals(port_code: str, repository: Any = Depends(get_arrivals_repository)):
    from risk_monitor.port_arrivals import get_port_arrivals

    try:
        return PortArrivalsResponse.model_validate(get_port_arrivals(port_code, repository=repository))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Port arrival data temporarily unavailable") from exc


@router.get("/ports/{port_code}/hourly")
def get_hourly_weather(port_code: str, start_utc: datetime, end_utc: datetime,
                       page: int = Query(1, ge=1), limit: int = Query(500, ge=1, le=1000),
                       repository: Any = Depends(get_weather_repository)):
    start, end = _utc(start_utc), _utc(end_utc)
    if end <= start:
        raise HTTPException(status_code=422, detail="end_utc must be after start_utc")
    return repository.get_hourly_weather(port_code, start, end, page=page, limit=limit)


@router.get("/ports/{port_code}/coverage")
def get_weather_coverage(port_code: str, repository: Any = Depends(get_weather_repository)):
    return repository.get_weather_coverage(port_code)


@router.get("/ports/{port_code}/profile")
def get_port_humidity_profile(port_code: str, eta_date: date,
                              eta_time: time | None = None,
                              rh_threshold: float = Query(85, ge=0, le=100),
                              repository: Any = Depends(get_weather_repository)):
    from 湿度模型.port_humidity.profile_service import get_humidity_profile

    if not isfinite(rh_threshold) or (eta_time is not None and
                                     (eta_time.minute or eta_time.second or eta_time.microsecond)):
        raise HTTPException(status_code=422, detail="RH threshold must be finite and ETA time a whole hour")
    result = get_humidity_profile(repository, port_code=port_code, eta_date=eta_date,
                                  eta_time=eta_time, rh_threshold=rh_threshold)
    if result is None:
        raise HTTPException(status_code=404, detail="No primary analysis location for port")
    return result


@router.get("/ports/{port_code}/seasonal")
def get_port_humidity_seasonal(port_code: str, month: int = Query(..., ge=1, le=12),
                               rh_threshold: float = Query(85, ge=0, le=100),
                               repository: Any = Depends(get_weather_repository)):
    from 湿度模型.port_humidity.seasonal_service import get_seasonal_humidity

    if not isfinite(rh_threshold):
        raise HTTPException(status_code=422, detail="RH threshold must be finite")
    result = get_seasonal_humidity(repository, port_code=port_code, month=month,
                                   rh_threshold=rh_threshold)
    if result is None:
        raise HTTPException(status_code=404, detail="No primary analysis location for port")
    return result

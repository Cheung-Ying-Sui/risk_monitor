from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from risk_monitor.eta_repository import get_sog_history
from risk_monitor.latest_position_repository import get_latest_position_by_vessel_id
from risk_monitor.navigation.destination_normalizer import resolve_destination
from risk_monitor.navigation.eta_engine import estimate_sailing_speed
from risk_monitor.navigation.route_monitor import evaluate_route_deviation
from risk_monitor.navigation.route_progress import calculate_route_progress
from risk_monitor.rolling_route_repository import get_active_route_prediction
from risk_monitor.vessel_query_repository import get_vessel_by_id


class NavigationPredictionNotFoundError(LookupError):
    pass


class NavigationPredictionDataError(ValueError):
    pass


class NavigationPredictionRepository:
    def get_vessel(self, vessel_id: str) -> dict[str, Any] | None:
        return get_vessel_by_id(vessel_id)

    def get_latest_position(self, vessel_id: str) -> dict[str, Any] | None:
        return get_latest_position_by_vessel_id(vessel_id)

    def get_active_route(self, mmsi: str) -> dict[str, Any] | None:
        return get_active_route_prediction(mmsi)

    def get_speed_history(
        self,
        mmsi: str,
        *,
        hours: int | None,
        now: datetime,
    ) -> list[dict[str, Any]]:
        return get_sog_history(mmsi, hours=hours, now=now)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif value is not None:
        normalized = str(value).strip()
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _ais_age_seconds(observed_at: Any, prediction_timestamp: datetime) -> float | None:
    observed = _parse_datetime(observed_at)
    if observed is None:
        return None
    return max(0.0, (prediction_timestamp - observed).total_seconds())


def _confidence(
    route_status: str,
    cross_track_error_nm: float,
    destination_confidence: float,
    speed_context: dict[str, Any],
    ais_age_seconds: float | None,
) -> float:
    speed_method = speed_context.get("speed_method")
    speed_confidence = {
        "recent_6h_moving_sog_median": 0.95,
        "recent_24h_moving_sog_median": 0.8,
        "historical_moving_sog_median": 0.65,
        "current_sog": 0.5,
    }.get(speed_method, 0.0)
    if ais_age_seconds is None:
        freshness_confidence = 0.3
    elif ais_age_seconds <= 15 * 60:
        freshness_confidence = 1.0
    elif ais_age_seconds <= 2 * 60 * 60:
        freshness_confidence = 0.85
    elif ais_age_seconds <= 24 * 60 * 60:
        freshness_confidence = 0.55
    else:
        freshness_confidence = 0.25

    if route_status == "on_route":
        route_confidence = 0.95
    elif cross_track_error_nm <= 16.0:
        route_confidence = 0.65
    else:
        route_confidence = 0.35

    return round(
        destination_confidence
        * speed_confidence
        * freshness_confidence
        * route_confidence,
        3,
    )


def _normalized_destination(value: Any) -> str | None:
    if value is None:
        return None
    normalized = "".join(str(value).strip().upper().split())
    return normalized or None


def _canonical_destination(value: Any) -> str | None:
    normalized = _normalized_destination(value)
    if normalized is None:
        return None
    resolution = resolve_destination(value)
    if resolution.get("resolution_status") == "resolved":
        return _normalized_destination(resolution.get("unlocode"))
    return normalized


class VesselNavigationPredictionService:
    def __init__(self, repository: NavigationPredictionRepository | None = None):
        self.repository = repository or NavigationPredictionRepository()

    def get_prediction(
        self,
        vessel_id: str,
        *,
        prediction_timestamp: datetime | None = None,
        strict_projection: bool = False,
    ) -> dict[str, Any]:
        normalized_vessel_id = str(vessel_id).strip()
        if not normalized_vessel_id:
            raise NavigationPredictionDataError("vessel_id is required.")

        vessel = self.repository.get_vessel(normalized_vessel_id)
        if not vessel:
            raise NavigationPredictionNotFoundError("Vessel not found.")
        mmsi = str(vessel.get("mmsi") or "").strip()
        if not mmsi:
            raise NavigationPredictionDataError("Vessel has no MMSI.")

        latest_position = self.repository.get_latest_position(normalized_vessel_id)
        if not latest_position:
            raise NavigationPredictionNotFoundError("Latest position not found.")
        active_route = self.repository.get_active_route(mmsi)
        if not active_route:
            raise NavigationPredictionNotFoundError("Active route prediction not found.")

        prediction_timestamp = prediction_timestamp or datetime.now(timezone.utc)
        if prediction_timestamp.tzinfo is None:
            prediction_timestamp = prediction_timestamp.replace(tzinfo=timezone.utc)
        prediction_timestamp = prediction_timestamp.astimezone(timezone.utc)

        try:
            progress = calculate_route_progress(
                latest_position,
                active_route.get("route_geojson"),
                reject_ambiguous=strict_projection,
            )
        except ValueError as exc:
            raise NavigationPredictionDataError(str(exc)) from exc

        recent_6h = self.repository.get_speed_history(
            mmsi, hours=6, now=prediction_timestamp
        )
        recent_24h = self.repository.get_speed_history(
            mmsi, hours=24, now=prediction_timestamp
        )
        historical = self.repository.get_speed_history(
            mmsi, hours=None, now=prediction_timestamp
        )
        speed_context = estimate_sailing_speed(
            recent_6h_positions=recent_6h,
            recent_24h_positions=recent_24h,
            historical_positions=historical,
            current_sog=latest_position.get("sog"),
        )
        speed_knots = speed_context.get("estimated_speed_knots")
        remaining_hours = (
            progress["remaining_distance_nm"] / speed_knots
            if speed_knots and speed_knots > 0
            else None
        )
        estimated_arrival_at = (
            prediction_timestamp + timedelta(hours=remaining_hours)
            if remaining_hours is not None
            else None
        )

        adherence = evaluate_route_deviation(
            latest_position,
            latest_position.get("cog"),
            active_route.get("route_geojson"),
        )
        route_status = adherence.get("status") or "unavailable"
        observed_at = latest_position.get("observed_at")
        ais_age_seconds = _ais_age_seconds(observed_at, prediction_timestamp)
        destination_confidence = (
            0.95 if active_route.get("destination_unlocode") else 0.75
        )
        confidence = _confidence(
            route_status,
            progress["cross_track_error_nm"],
            destination_confidence,
            speed_context,
            ais_age_seconds,
        )
        warnings = list(speed_context.get("warnings") or [])
        observed = _parse_datetime(observed_at)
        if observed is None:
            warnings.append("invalid_ais_observed_at")
        elif observed > prediction_timestamp + timedelta(minutes=5):
            warnings.append("ais_timestamp_in_future")
        elif ais_age_seconds is not None and ais_age_seconds > 24 * 60 * 60:
            warnings.append("stale_ais")

        if route_status == "deviating":
            warnings.append("route_deviation_detected")
        latest_ais_destination = latest_position.get("destination")
        latest_destination_key = _canonical_destination(latest_ais_destination)
        route_destination_keys = {
            key
            for key in (
                _canonical_destination(active_route.get("destination_unlocode")),
                _canonical_destination(active_route.get("destination_normalized")),
                _canonical_destination(active_route.get("destination_raw")),
            )
            if key
        }
        destination_matches_latest_ais = (
            latest_destination_key in route_destination_keys
            if latest_destination_key and route_destination_keys
            else None
        )
        if destination_matches_latest_ais is False:
            warnings.append("active_route_destination_mismatch")

        return {
            "status": "estimated" if remaining_hours is not None else "partial",
            "vessel_id": normalized_vessel_id,
            "mmsi": mmsi,
            "prediction_timestamp": prediction_timestamp.isoformat(),
            "based_on_observed_at": observed_at,
            "destination": {
                "port_id": active_route.get("destination_unlocode"),
                "name": active_route.get("destination_normalized")
                or active_route.get("destination_raw"),
                "confidence": destination_confidence,
            },
            "route": {
                "prediction_id": active_route.get("route_prediction_id"),
                "version": active_route.get("route_version"),
                "geojson": active_route.get("route_geojson"),
                "remaining_geojson": progress["remaining_route_geojson"],
                "remaining_distance_nm": progress["remaining_distance_nm"],
                "total_distance_nm": progress["total_route_distance_nm"],
                "progress": progress["route_progress"],
                "cross_track_error_nm": progress["cross_track_error_nm"],
                "cross_track_error_m": progress["cross_track_error_m"],
                "projected_position": progress["projected_position"],
                "source": active_route.get("route_method") or "persisted_route",
                "status": route_status,
                "latest_ais_destination": latest_ais_destination,
                "destination_matches_latest_ais": destination_matches_latest_ais,
            },
            "eta": {
                "estimated_arrival_at": (
                    estimated_arrival_at.isoformat()
                    if estimated_arrival_at is not None
                    else None
                ),
                "remaining_hours": remaining_hours,
                "estimated_speed_knots": speed_knots,
                "speed_method": speed_context.get("speed_method"),
                "speed_sample_count": speed_context.get("speed_sample_count") or 0,
                "speed_variability": speed_context.get("speed_variability"),
                "confidence": confidence,
            },
            "risk_zone_crossings": [],
            "prediction_quality": {
                "confidence": confidence,
                "ais_age_seconds": ais_age_seconds,
                "reroute_reason": active_route.get("route_update_reason"),
                "warnings": warnings,
            },
        }

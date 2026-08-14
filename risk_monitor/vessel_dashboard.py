import time
import sys
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from risk_monitor.collection_log_repository import get_latest_collection_run
from risk_monitor.eta_repository import get_vessel_eta_estimate
from risk_monitor.latest_position_repository import get_latest_positions
from risk_monitor.position_repository import upsert_position
from risk_monitor.risk_repository import (
    get_active_risk_zones_geojson,
    get_vessel_current_risk,
)
from risk_monitor.route_candidate_comparison_repository import (
    compare_route_candidates,
)
from risk_monitor.route_evaluation_repository import (
    evaluate_route_prediction,
    get_route_prediction_history,
)
from risk_monitor.rolling_route_repository import (
    ROUTE_UPDATE_REASON_MANUAL_REFRESH,
    get_rolling_route_prediction,
)
from risk_monitor.navigation.shipping_lane_provider import (
    load_official_routeing_reference,
)
from risk_monitor.tracking_repository import (
    add_tracking_vessel,
    disable_tracking_vessel,
    get_tracking_status,
)
from risk_monitor.trajectory_repository import get_vessel_track
from risk_monitor.vessel_live_query_repository import search_vessel_live
from risk_monitor.vessel_repository import upsert_vessel


st.set_page_config(
    page_title="Vessel Risk Monitor Dashboard",
    layout="wide",
)


def _to_dataframe(records):
    if not records:
        return pd.DataFrame()

    return pd.DataFrame(records)


def _valid_position_dataframe(records):
    dataframe = _to_dataframe(records)
    if dataframe.empty:
        return dataframe

    return dataframe.dropna(
        subset=[
            "latitude",
            "longitude",
        ]
    ).rename(
        columns={
            "latitude": "lat",
            "longitude": "lon",
        }
    )


def _display_metrics(record, fields):
    columns = st.columns(len(fields))

    for column, (label, key) in zip(
        columns,
        fields,
    ):
        value = "-"
        if record:
            value = record.get(key)
            if value is None:
                value = "-"

        column.metric(
            label,
            value,
        )


def _route_coordinates(eta_result):
    route_geojson = (eta_result or {}).get("estimated_route_geojson") or {}
    if route_geojson.get("type") != "LineString":
        return []

    coordinates = route_geojson.get("coordinates") or []
    return [
        coordinate
        for coordinate in coordinates
        if isinstance(coordinate, list)
        and len(coordinate) >= 2
        and coordinate[0] is not None
        and coordinate[1] is not None
    ]


def _estimated_route_layer(eta_result):
    coordinates = _route_coordinates(eta_result)
    if len(coordinates) < 2:
        return []

    return [
        pdk.Layer(
            "PathLayer",
            data=[
                {
                    "path": coordinates,
                    "layer_name": "Estimated Route",
                    "route_method": eta_result.get("route_method"),
                    "distance_method": eta_result.get("distance_method"),
                }
            ],
            get_path="path",
            get_color=[
                245,
                158,
                11,
                210,
            ],
            width_min_pixels=3,
            pickable=True,
        )
    ]


def _destination_marker_layer(eta_result):
    if not eta_result:
        return []

    latitude = eta_result.get("destination_latitude")
    longitude = eta_result.get("destination_longitude")
    if latitude is None or longitude is None:
        return []

    destination_data = pd.DataFrame(
        [
            {
                "lat": latitude,
                "lon": longitude,
                "layer_name": "Destination",
                "destination": eta_result.get("destination_normalized")
                or eta_result.get("destination_raw"),
                "unlocode": eta_result.get("destination_unlocode") or "-",
                "baseline_eta": eta_result.get("baseline_estimated_eta") or "-",
            }
        ]
    )

    return [
        pdk.Layer(
            "ScatterplotLayer",
            data=destination_data,
            get_position="[lon, lat]",
            get_radius=260,
            get_fill_color=[
                22,
                163,
                74,
                230,
            ],
            pickable=True,
        )
    ]


def _route_legend():
    st.caption(
        "Legend: Vessel = red marker | Historical Track = blue line | "
        "Estimated Route = amber line | JWLA Listed Area = red polygon | "
        "Destination = green marker"
    )


def _route_disclaimer():
    st.caption(
        "Estimated route is a baseline approximation for insurance risk "
        "analysis. It is not intended for vessel navigation or operational "
        "route planning."
    )


def _single_position_chart(position, eta_result=None):
    map_data = _valid_position_dataframe([position])
    if map_data.empty:
        st.info("No valid current coordinates available.")
        return

    point = map_data.iloc[0]
    risk_zone_layers = _risk_zone_layers()

    st.pydeck_chart(
        pdk.Deck(
            map_style=None,
            initial_view_state=pdk.ViewState(
                latitude=float(point["lat"]),
                longitude=float(point["lon"]),
                zoom=11,
                pitch=0,
            ),
            layers=[
                *risk_zone_layers,
                *_estimated_route_layer(eta_result),
                *_destination_marker_layer(eta_result),
                pdk.Layer(
                    "ScatterplotLayer",
                    data=map_data,
                    get_position="[lon, lat]",
                    get_radius=180,
                    get_fill_color=[
                        220,
                        60,
                        40,
                        220,
                    ],
                    pickable=True,
                )
            ],
            tooltip={
                "text": (
                    "Zone Name: {zone_name}\n"
                    "Source: {source}\n"
                    "Source Document: {source_document}\n"
                    "MMSI: {mmsi}\n"
                    "Observed: {observed_at}\n"
                    "SOG: {sog}\n"
                    "COG: {cog}\n"
                    "Layer: {layer_name}\n"
                    "Destination: {destination}\n"
                    "UN/LOCODE: {unlocode}\n"
                    "Baseline ETA: {baseline_eta}"
                )
            },
        )
    )
    if eta_result:
        _route_legend()
        _route_disclaimer()


def _risk_zone_feature_collection():
    try:
        active_zones = get_active_risk_zones_geojson()
    except Exception:
        st.info("Risk zone layer unavailable")
        return None

    features = []
    for zone in active_zones:
        geometry = zone.get("geometry_geojson")
        if not geometry:
            continue

        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "zone_id": zone.get("zone_id"),
                    "zone_version_id": zone.get("zone_version_id"),
                    "zone_name": zone.get("zone_name"),
                    "zone_type": zone.get("zone_type"),
                    "source": zone.get("source"),
                    "source_document": zone.get("source_document"),
                    "effective_date": zone.get("effective_date"),
                },
            }
        )

    if not features:
        return None

    return {
        "type": "FeatureCollection",
        "features": features,
    }


def _risk_zone_layers():
    feature_collection = _risk_zone_feature_collection()
    if not feature_collection:
        return []

    return [
        pdk.Layer(
            "GeoJsonLayer",
            data=feature_collection,
            pickable=True,
            stroked=True,
            filled=True,
            get_fill_color=[
                220,
                60,
                40,
                45,
            ],
            get_line_color=[
                180,
                35,
                35,
                190,
            ],
            get_line_width=2,
        )
    ]


def _has_current_position(vessel):
    return bool(
        vessel
        and vessel.get("latitude") is not None
        and vessel.get("longitude") is not None
        and vessel.get("observed_at") is not None
    )


def render_risk_status(vessel):
    st.subheader("JWLA Risk Status")

    if not vessel:
        st.info("Search a vessel to view JWLA risk status.")
        return

    mmsi = vessel.get("mmsi")
    if not mmsi:
        st.warning("Risk status unavailable: vessel has no MMSI.")
        return

    if not _has_current_position(vessel):
        st.info("Risk status unavailable: no latest position available.")
        return

    try:
        risk_hits = get_vessel_current_risk(mmsi)
    except Exception as exc:
        st.warning(f"Risk status unavailable: {exc}")
        return

    if not risk_hits:
        col_status, col_area = st.columns(2)
        col_status.metric("JWLA Risk Status", "CLEAR")
        col_area.metric("Current Listed Area", "None")
        st.info(
            "CLEAR means the current latest vessel position does not intersect "
            "an active JWLA Listed Area."
        )
        return

    st.warning("JWLA Risk Status: IN LISTED AREA")
    st.metric("Listed Area Hits", len(risk_hits))

    dataframe = _to_dataframe(risk_hits)
    if dataframe.empty:
        st.warning("Risk status unavailable: invalid risk response.")
        return

    if "source" not in dataframe.columns:
        dataframe["source"] = "JWLA"

    visible_columns = [
        "zone_name",
        "zone_type",
        "source",
        "source_document",
        "effective_date",
        "observed_at",
    ]
    st.dataframe(
        dataframe[
            [
                column
                for column in visible_columns
                if column in dataframe.columns
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )


def _all_positions_chart(positions):
    map_data = _valid_position_dataframe(positions)
    if map_data.empty:
        st.info("No valid current vessel positions available.")
        return

    first_point = map_data.iloc[0]
    risk_zone_layers = _risk_zone_layers()

    st.pydeck_chart(
        pdk.Deck(
            map_style=None,
            initial_view_state=pdk.ViewState(
                latitude=float(first_point["lat"]),
                longitude=float(first_point["lon"]),
                zoom=4,
                pitch=0,
            ),
            layers=[
                *risk_zone_layers,
                pdk.Layer(
                    "ScatterplotLayer",
                    data=map_data,
                    get_position="[lon, lat]",
                    get_radius=180,
                    get_fill_color=[
                        220,
                        60,
                        40,
                        220,
                    ],
                    pickable=True,
                ),
            ],
            tooltip={
                "text": (
                    "Zone Name: {zone_name}\n"
                    "Source: {source}\n"
                    "Source Document: {source_document}\n"
                    "MMSI: {mmsi}\n"
                    "Observed: {observed_at}"
                )
            },
        )
    )


def _track_chart(track_points, current_index, eta_result=None):
    map_data = _valid_position_dataframe(track_points)
    if map_data.empty:
        st.info("No valid historical coordinates available.")
        return

    map_data = map_data.sort_values("observed_at").reset_index(drop=True)
    current_index = max(
        0,
        min(
            int(current_index),
            len(map_data) - 1,
        ),
    )
    visible_data = map_data.iloc[: current_index + 1]
    current_point = visible_data.iloc[-1]
    path = visible_data[
        [
            "lon",
            "lat",
        ]
    ].values.tolist()
    risk_zone_layers = _risk_zone_layers()

    st.pydeck_chart(
        pdk.Deck(
            map_style=None,
            initial_view_state=pdk.ViewState(
                latitude=float(current_point["lat"]),
                longitude=float(current_point["lon"]),
                zoom=11,
                pitch=0,
            ),
            layers=[
                *risk_zone_layers,
                pdk.Layer(
                    "PathLayer",
                    data=[
                        {
                            "path": path,
                        }
                    ],
                    get_path="path",
                    get_color=[
                        32,
                        120,
                        180,
                    ],
                    width_min_pixels=4,
                ),
                *_estimated_route_layer(eta_result),
                *_destination_marker_layer(eta_result),
                pdk.Layer(
                    "ScatterplotLayer",
                    data=visible_data,
                    get_position="[lon, lat]",
                    get_radius=70,
                    get_fill_color=[
                        20,
                        110,
                        220,
                        100,
                    ],
                    pickable=True,
                ),
                pdk.Layer(
                    "ScatterplotLayer",
                    data=pd.DataFrame([current_point]),
                    get_position="[lon, lat]",
                    get_radius=180,
                    get_fill_color=[
                        220,
                        60,
                        40,
                        230,
                    ],
                    pickable=True,
                ),
            ],
            tooltip={
                "text": (
                    "Zone Name: {zone_name}\n"
                    "Source: {source}\n"
                    "Source Document: {source_document}\n"
                    "MMSI: {mmsi}\n"
                    "Observed: {observed_at}\n"
                    "SOG: {sog}\n"
                    "COG: {cog}\n"
                    "Layer: {layer_name}\n"
                    "Destination: {destination}\n"
                    "UN/LOCODE: {unlocode}\n"
                    "Baseline ETA: {baseline_eta}"
                )
            },
        )
    )
    if eta_result:
        _route_legend()
        _route_disclaimer()


def render_vessel_search():
    st.subheader("A. Vessel Search")

    if "live_vessel" not in st.session_state:
        st.session_state.live_vessel = None

    col_type, col_query = st.columns(
        [
            1,
            3,
        ]
    )
    search_type = col_type.radio(
        "Search Type",
        [
            "MMSI",
            "IMO",
        ],
        horizontal=True,
    )
    query = col_query.text_input(
        "MMSI / IMO",
        placeholder="Enter MMSI or IMO",
    )

    if st.button("Search Chinaports"):
        normalized_query = query.strip()
        if not normalized_query:
            st.warning("Please enter an MMSI or IMO.")
            return st.session_state.live_vessel

        try:
            st.session_state.live_vessel = search_vessel_live(
                normalized_query,
                search_type=search_type.lower(),
            )
        except Exception as exc:
            st.session_state.live_vessel = None
            st.error(f"Chinaports query failed: {exc}")
            return None

        if not st.session_state.live_vessel:
            st.warning("No vessel found from Chinaports.")
            return None

    vessel = st.session_state.live_vessel
    if not vessel:
        st.info("Search Chinaports by MMSI or IMO to inspect a vessel.")
        return None

    if vessel.get("dashboard_source") == "supabase":
        warning = vessel.get("dashboard_warning")
        message = "Showing vessel data from Supabase because Chinaports is unavailable."
        if warning:
            message = f"{message} Chinaports error: {warning}"
        st.warning(message)

    _display_metrics(
        vessel,
        [
            ("Ship Name", "ship_name"),
            ("MMSI", "mmsi"),
            ("IMO", "imo"),
            ("Call Sign", "callsign"),
            ("Flag", "flag_state"),
            ("Ship Type", "ship_type"),
            ("Gross Tonnage", "gross_tonnage"),
        ],
    )

    return vessel


def render_tracking_control(vessel):
    st.subheader("B. Tracking Control")

    if not vessel:
        st.info("Search a vessel before managing tracking.")
        return

    mmsi = vessel.get("mmsi")
    if not mmsi:
        st.warning("This Chinaports result has no MMSI, so it cannot be tracked.")
        return

    try:
        tracking_status = get_tracking_status(mmsi)
    except Exception as exc:
        tracking_status = None
        st.error(f"Tracking status query failed: {exc}")

    is_active = bool(
        tracking_status
        and tracking_status.get("is_active")
    )
    tracking_mode = "-"
    if tracking_status:
        tracking_mode = tracking_status.get("tracking_mode") or "-"

    col_start, col_stop, col_status, col_mode = st.columns(4)

    if col_start.button(
        "Start Tracking",
        disabled=is_active,
    ):
        try:
            vessel_result = upsert_vessel(vessel)
            vessel_id = None
            if vessel_result:
                vessel_id = vessel_result[0].get("id")

            raw_data = vessel.get("raw_data") or vessel
            upsert_position(raw_data)
            add_tracking_vessel(
                mmsi,
                tracking_mode="history_tracking",
                priority=0,
                vessel_id=vessel_id,
            )
            st.success("Tracking enabled")
            st.rerun()
        except Exception as exc:
            st.error(f"Start tracking failed: {exc}")

    if col_stop.button(
        "Stop Tracking",
        disabled=not is_active,
    ):
        try:
            disable_tracking_vessel(mmsi)
            st.success("Tracking disabled")
            st.rerun()
        except Exception as exc:
            st.error(f"Stop tracking failed: {exc}")

    col_status.metric(
        "Tracking",
        "ACTIVE" if is_active else "INACTIVE",
    )
    col_mode.metric(
        "Mode",
        tracking_mode,
    )


def _get_eta_result(vessel):
    if not vessel or not vessel.get("mmsi"):
        return None

    try:
        return get_vessel_eta_estimate(vessel.get("mmsi"))
    except Exception as exc:
        return {
            "status": "unavailable",
            "warnings": [
                f"ETA unavailable: {exc}",
            ],
        }


def _get_rolling_route_result(vessel):
    if not vessel or not vessel.get("mmsi"):
        return None

    mmsi = str(vessel.get("mmsi"))
    manual_refresh_key = f"rolling_route_manual_refresh_{mmsi}"
    update_reason = None
    if st.session_state.get(manual_refresh_key):
        update_reason = ROUTE_UPDATE_REASON_MANUAL_REFRESH
        st.session_state[manual_refresh_key] = False

    try:
        result = get_rolling_route_prediction(
            mmsi,
            update_reason=update_reason,
        )
    except Exception as exc:
        return {
            "status": "unavailable",
            "warnings": [
                f"Rolling route unavailable: {exc}",
            ],
        }

    return result


def render_current_position(vessel, eta_result=None):
    st.subheader("C. Current Position")

    if not vessel:
        st.info("Search a vessel to view its live position.")
        latest_positions = get_latest_positions()
        _all_positions_chart(latest_positions)
        return

    _display_metrics(
        vessel,
        [
            ("Latitude", "latitude"),
            ("Longitude", "longitude"),
            ("SOG", "sog"),
            ("COG", "cog"),
            ("Heading", "heading"),
            ("Observed Time", "observed_at"),
        ],
    )
    _single_position_chart(vessel, eta_result=eta_result)
    render_risk_status(vessel)


def _format_number(value, suffix="", decimals=1):
    if value is None:
        return "-"

    try:
        return f"{float(value):,.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return "-"


def _format_upper(value):
    if not value:
        return "-"

    return str(value).upper()


def _user_friendly_eta_warnings(warnings):
    messages = []
    for warning in warnings or []:
        if str(warning).startswith("regional_corridor:"):
            message = "Estimated route uses a regional baseline maritime corridor."
        elif "navigable_route_unavailable" in str(warning):
            message = (
                "Navigable route estimate unavailable. ETA falls back to "
                "great-circle distance."
            )
        elif warning == "destination_unresolved":
            message = "Destination could not be resolved to a verified port."
        elif warning == "destination_not_port":
            message = "Destination text does not describe a port."
        else:
            message = str(warning).replace("_", " ").capitalize()
        if message not in messages:
            messages.append(message)
    return messages


def _route_status_label(status):
    if status == "on_route":
        return "ON EXPECTED ROUTE"
    if status == "deviating":
        return "ROUTE DEVIATION DETECTED"
    if status == "awaiting_new_ais_position":
        return "AWAITING NEW AIS POSITION"
    if status == "awaiting_data":
        return "AWAITING NEW AIS DATA"
    if status == "insufficient_data":
        return "INSUFFICIENT AIS DATA"
    if status == "following_prediction":
        return "FOLLOWING PREDICTION"
    if status == "superseded":
        return "SUPERSEDED"
    return "UNAVAILABLE"


def render_eta_estimate(vessel, eta_result=None):
    st.subheader("D. ETA Estimate")

    if not vessel or not vessel.get("mmsi"):
        st.info("Search a vessel with MMSI to view baseline ETA.")
        return

    if eta_result is None:
        eta_result = _get_eta_result(vessel)

    warnings = eta_result.get("warnings") or []
    if eta_result.get("status") != "estimated":
        friendly_warnings = _user_friendly_eta_warnings(warnings)
        reason = ", ".join(friendly_warnings) if friendly_warnings else "unavailable"
        st.info(f"ETA unavailable: {reason}")
        destination_raw = eta_result.get("destination_raw")
        if destination_raw:
            st.metric("Destination", destination_raw)
        return

    col_destination, col_distance, col_speed = st.columns(3)
    col_time, col_eta, col_confidence = st.columns(3)

    col_destination.metric(
        "Destination",
        eta_result.get("destination_normalized")
        or eta_result.get("destination_raw")
        or "-",
    )
    col_distance.metric(
        "Remaining Distance",
        _format_number(
            eta_result.get("remaining_distance_nm"),
            suffix=" nm",
        ),
    )
    col_speed.metric(
        "Estimated Sailing Speed",
        _format_number(
            eta_result.get("estimated_speed_knots"),
            suffix=" kn",
        ),
    )
    col_time.metric(
        "Estimated Time Remaining",
        _format_number(
            eta_result.get("estimated_remaining_hours"),
            suffix=" h",
        ),
    )
    col_eta.metric(
        "Baseline ETA",
        eta_result.get("baseline_estimated_eta") or "-",
    )
    col_confidence.metric(
        "Confidence",
        _format_upper(eta_result.get("confidence")),
    )
    st.metric(
        "Route Method",
        eta_result.get("route_method")
        or eta_result.get("distance_method")
        or "-",
    )

    if eta_result.get("distance_method") == "navigable_route_baseline":
        col_gc, col_route, col_ratio = st.columns(3)
        col_gc.metric(
            "Great-circle Distance",
            _format_number(
                eta_result.get("great_circle_distance_nm"),
                suffix=" nm",
            ),
        )
        col_route.metric(
            "Navigable Distance",
            _format_number(
                eta_result.get("navigable_distance_nm"),
                suffix=" nm",
            ),
        )
        col_ratio.metric(
            "Route Ratio",
            _format_number(
                eta_result.get("route_distance_ratio"),
                decimals=3,
            ),
        )

    if eta_result.get("reported_ais_eta"):
        col_reported, col_baseline, col_delta = st.columns(3)
        col_reported.metric(
            "AIS Reported ETA",
            eta_result.get("reported_ais_eta"),
        )
        col_baseline.metric(
            "Baseline ETA",
            eta_result.get("baseline_estimated_eta") or "-",
        )
        col_delta.metric(
            "ETA Difference",
            _format_number(
                eta_result.get("eta_difference_hours"),
                suffix=" h",
            ),
        )

    if warnings:
        st.caption(
            "ETA warnings: "
            f"{' '.join(_user_friendly_eta_warnings(warnings))}"
        )

    st.caption(
        "Baseline ETA is an indicative estimate based on current position, "
        "destination and recent vessel speed. It does not account for "
        "navigable route constraints, weather, congestion, waiting time or "
        "operational changes."
    )


def render_route_monitoring_status(vessel, rolling_route_result=None):
    st.subheader("E. Route Monitoring Status")

    if not vessel or not vessel.get("mmsi"):
        st.info("Search a vessel with MMSI to view route monitoring.")
        return

    mmsi = str(vessel.get("mmsi"))
    manual_refresh_key = f"rolling_route_manual_refresh_{mmsi}"
    if st.button("Manual Route Refresh"):
        st.session_state[manual_refresh_key] = True
        st.rerun()

    if not rolling_route_result or rolling_route_result.get("status") != "estimated":
        warnings = (rolling_route_result or {}).get("warnings") or []
        reason = ", ".join(warnings) if warnings else "unavailable"
        st.info(f"Route monitoring unavailable: {reason}")
        return

    active_route = rolling_route_result.get("active_route") or {}
    deviation_result = rolling_route_result.get("deviation_result")
    if not deviation_result:
        deviation_result = {
            "status": "on_route",
            "distance_to_route_nm": 0,
            "expected_route_bearing_deg": None,
            "current_cog_deg": vessel.get("cog"),
            "course_difference_deg": None,
            "recalculation_recommended": False,
            "consecutive_deviation_points": 0,
            "required_consecutive_deviation_points": 3,
        }

    status = deviation_result.get("status")
    if status == "deviating":
        st.warning(_route_status_label(status))
    elif status == "on_route":
        st.success(_route_status_label(status))
    else:
        st.info(_route_status_label(status))

    col_version, col_created, col_origin = st.columns(3)
    col_since, col_new_points, col_reason = st.columns(3)
    col_distance, col_course, col_expected = st.columns(3)
    col_recalc, col_current, col_status = st.columns(3)
    col_version.metric(
        "Route Version",
        active_route.get("route_version") or "-",
    )
    col_created.metric(
        "Route Created At",
        active_route.get("route_created_at") or "-",
    )
    col_origin.metric(
        "Origin Position",
        active_route.get("origin_position_id") or "-",
    )
    col_since.metric(
        "Monitoring Since",
        rolling_route_result.get("monitoring_since") or "-",
    )
    col_new_points.metric(
        "New AIS Observations",
        rolling_route_result.get("new_ais_points_since_prediction", 0),
    )
    col_reason.metric(
        "Route Update Reason",
        active_route.get("route_update_reason") or "-",
    )
    col_distance.metric(
        "Distance to Predicted Route",
        _format_number(
            deviation_result.get("distance_to_route_nm"),
            suffix=" nm",
        ),
    )
    col_course.metric(
        "Course Difference",
        _format_number(
            deviation_result.get("course_difference_deg"),
            suffix=" deg",
        ),
    )
    col_expected.metric(
        "Expected Route Bearing",
        _format_number(
            deviation_result.get("expected_route_bearing_deg"),
            suffix=" deg",
        ),
    )
    col_recalc.metric(
        "Reroute Recommended",
        "YES" if deviation_result.get("recalculation_recommended") else "NO",
    )
    col_current.metric(
        "Current COG",
        _format_number(
            deviation_result.get("current_cog_deg"),
            suffix=" deg",
        ),
    )
    col_status.metric(
        "Route Status",
        _route_status_label(status),
    )

    st.caption(
        "Consecutive deviation points: "
        f"{deviation_result.get('consecutive_deviation_points', 0)} / "
        f"{deviation_result.get('required_consecutive_deviation_points', 3)}"
    )
    reasons = deviation_result.get("reasons") or []
    if reasons:
        st.caption(f"Route monitoring reasons: {', '.join(reasons)}")


def _route_prediction_destination_layer(route_geojson):
    coordinates = (route_geojson or {}).get("coordinates") or []
    if not coordinates:
        return []

    longitude, latitude = coordinates[-1][:2]
    return [
        pdk.Layer(
            "ScatterplotLayer",
            data=pd.DataFrame(
                [
                    {
                        "lat": latitude,
                        "lon": longitude,
                        "layer_name": "Destination",
                    }
                ]
            ),
            get_position="[lon, lat]",
            get_radius=260,
            get_fill_color=[
                22,
                163,
                74,
                230,
            ],
            pickable=True,
        )
    ]


def _route_prediction_playback_chart(evaluation_result):
    predicted_route = evaluation_result.get("predicted_route")
    coordinates = (predicted_route or {}).get("coordinates") or []
    if len(coordinates) < 2:
        st.info("No valid predicted route geometry available.")
        return

    actual_track = evaluation_result.get("actual_track") or []
    actual_data = _valid_position_dataframe(actual_track)
    first_lon, first_lat = coordinates[0][:2]
    layers = [
        *_risk_zone_layers(),
        pdk.Layer(
            "PathLayer",
            data=[
                {
                    "path": coordinates,
                    "layer_name": "Predicted Route",
                }
            ],
            get_path="path",
            get_color=[
                245,
                158,
                11,
                220,
            ],
            width_min_pixels=4,
            pickable=True,
        ),
        *_route_prediction_destination_layer(predicted_route),
    ]

    if not actual_data.empty:
        actual_path = actual_data[
            [
                "lon",
                "lat",
            ]
        ].values.tolist()
        last_actual = actual_data.iloc[-1]
        layers.extend(
            [
                pdk.Layer(
                    "PathLayer",
                    data=[
                        {
                            "path": actual_path,
                            "layer_name": "Actual AIS Track",
                        }
                    ],
                    get_path="path",
                    get_color=[
                        14,
                        165,
                        233,
                        230,
                    ],
                    width_min_pixels=4,
                    pickable=True,
                ),
                pdk.Layer(
                    "ScatterplotLayer",
                    data=actual_data,
                    get_position="[lon, lat]",
                    get_radius=80,
                    get_fill_color=[
                        14,
                        165,
                        233,
                        130,
                    ],
                    pickable=True,
                ),
                pdk.Layer(
                    "ScatterplotLayer",
                    data=pd.DataFrame([last_actual]),
                    get_position="[lon, lat]",
                    get_radius=190,
                    get_fill_color=[
                        220,
                        60,
                        40,
                        230,
                    ],
                    pickable=True,
                ),
            ]
        )

    st.pydeck_chart(
        pdk.Deck(
            map_style=None,
            initial_view_state=pdk.ViewState(
                latitude=float(first_lat),
                longitude=float(first_lon),
                zoom=4,
                pitch=0,
            ),
            layers=layers,
            tooltip={
                "text": (
                    "Layer: {layer_name}\n"
                    "MMSI: {mmsi}\n"
                    "Observed: {observed_at}\n"
                    "SOG: {sog}\n"
                    "COG: {cog}"
                )
            },
        )
    )
    st.caption(
        "Legend: Predicted Route = amber line | Actual Track = blue line | "
        "Destination = green marker | JWLA = red polygon"
    )


def render_route_prediction_history(vessel):
    st.subheader("F. Route Prediction History")

    if not vessel or not vessel.get("mmsi"):
        st.info("Search a vessel with MMSI to view prediction history.")
        return

    mmsi = str(vessel.get("mmsi"))
    try:
        history = get_route_prediction_history(mmsi)
    except Exception as exc:
        st.error(f"Route prediction history query failed: {exc}")
        return

    if not history:
        st.info("No route prediction history found.")
        return

    history_dataframe = _to_dataframe(history)
    visible_columns = [
        "route_version",
        "route_created_at",
        "superseded_at",
        "destination_normalized",
        "destination_unlocode",
        "route_update_reason",
        "status",
    ]
    st.dataframe(
        history_dataframe[
            [
                column
                for column in visible_columns
                if column in history_dataframe.columns
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    options = [
        int(route_prediction.get("route_version"))
        for route_prediction in history
        if route_prediction.get("route_version") is not None
    ]
    if not options:
        st.info("Route versions are unavailable.")
        return

    selected_version = st.selectbox(
        "Prediction Version",
        options=options,
        index=len(options) - 1,
    )

    try:
        evaluation = evaluate_route_prediction(
            mmsi,
            route_version=selected_version,
        )
    except Exception as exc:
        st.error(f"Route prediction evaluation failed: {exc}")
        return

    route_prediction = evaluation.get("route_prediction") or {}
    status = evaluation.get("status")
    if status in {"awaiting_data", "insufficient_data"}:
        st.info(_route_status_label(status))
    elif status == "deviating":
        st.warning(_route_status_label(status))
    else:
        st.success(_route_status_label(status))

    col_version, col_count, col_status = st.columns(3)
    col_mean, col_median, col_max = st.columns(3)
    col_p90, col_adherence, col_progress = st.columns(3)
    col_version.metric(
        "Prediction Version",
        route_prediction.get("route_version") or "-",
    )
    col_count.metric(
        "Observation Count",
        evaluation.get("observation_count") or 0,
    )
    col_status.metric(
        "Evaluation Status",
        _route_status_label(status),
    )
    col_mean.metric(
        "Mean Route Deviation",
        _format_number(
            evaluation.get("mean_deviation_nm"),
            suffix=" nm",
        ),
    )
    col_median.metric(
        "Median Route Deviation",
        _format_number(
            evaluation.get("median_deviation_nm"),
            suffix=" nm",
        ),
    )
    col_max.metric(
        "Maximum Route Deviation",
        _format_number(
            evaluation.get("max_deviation_nm"),
            suffix=" nm",
        ),
    )
    col_p90.metric(
        "P90 Route Deviation",
        _format_number(
            evaluation.get("p90_deviation_nm"),
            suffix=" nm",
        ),
    )
    col_adherence.metric(
        "Route Adherence Ratio",
        _format_number(
            evaluation.get("route_adherence_ratio"),
            decimals=3,
        ),
    )
    col_progress.metric(
        "Route Progress",
        _format_number(
            evaluation.get("route_progress_ratio"),
            decimals=3,
        ),
    )

    _route_prediction_playback_chart(evaluation)

    point_errors = evaluation.get("point_errors") or []
    if point_errors:
        st.dataframe(
            _to_dataframe(point_errors),
            use_container_width=True,
            hide_index=True,
        )


def _route_bbox(route_coordinates):
    return {
        "min_lon": min(coordinate[0] for coordinate in route_coordinates),
        "max_lon": max(coordinate[0] for coordinate in route_coordinates),
        "min_lat": min(coordinate[1] for coordinate in route_coordinates),
        "max_lat": max(coordinate[1] for coordinate in route_coordinates),
    }


def _bbox_intersects(left, right):
    return not (
        left["max_lat"] < right["min_lat"]
        or left["min_lat"] > right["max_lat"]
        or left["max_lon"] < right["min_lon"]
        or left["min_lon"] > right["max_lon"]
    )


def _official_routeing_layers(route_coordinates):
    if not route_coordinates:
        return []

    route_bbox = _route_bbox(route_coordinates)
    expanded_bbox = {
        "min_lon": route_bbox["min_lon"] - 1,
        "max_lon": route_bbox["max_lon"] + 1,
        "min_lat": route_bbox["min_lat"] - 1,
        "max_lat": route_bbox["max_lat"] + 1,
    }
    reference = load_official_routeing_reference()
    features = []
    for feature in reference.get("features") or []:
        if feature.get("type") not in {
            "traffic_lane",
            "recommended_track",
            "deep_water_route",
            "precautionary_area",
        }:
            continue
        feature_bbox = feature.get("bbox")
        if not feature_bbox or not _bbox_intersects(feature_bbox, expanded_bbox):
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "layer_name": "Official Routeing Measure",
                    "name": feature.get("name"),
                    "routeing_type": feature.get("type"),
                    "official": feature.get("official"),
                },
                "geometry": feature.get("geometry"),
            }
        )
        if len(features) >= 20:
            break

    if not features:
        return []

    return [
        pdk.Layer(
            "GeoJsonLayer",
            data={
                "type": "FeatureCollection",
                "features": features,
            },
            pickable=True,
            stroked=True,
            filled=True,
            get_fill_color=[
                34,
                197,
                94,
                55,
            ],
            get_line_color=[
                22,
                101,
                52,
                210,
            ],
            get_line_width=2,
        )
    ]


def _candidate_comparison_chart(comparison_result, show_official_measures=False):
    current_route = comparison_result.get("current_route") or {}
    candidate = comparison_result.get("official_ranked_candidate") or {}
    actual_track = comparison_result.get("actual_track") or []
    current_coordinates = (current_route.get("route_geojson") or {}).get(
        "coordinates"
    ) or []
    candidate_coordinates = (
        candidate.get("estimated_route_geojson") or {}
    ).get("coordinates") or []
    if len(current_coordinates) < 2:
        st.info("No valid current route geometry available for comparison.")
        return

    first_lon, first_lat = current_coordinates[0][:2]
    layers = [
        *_risk_zone_layers(),
        *(
            _official_routeing_layers(current_coordinates)
            if show_official_measures
            else []
        ),
        pdk.Layer(
            "PathLayer",
            data=[
                {
                    "path": current_coordinates,
                    "layer_name": "Current Predicted Route",
                }
            ],
            get_path="path",
            get_color=[
                245,
                158,
                11,
                210,
            ],
            width_min_pixels=4,
            pickable=True,
        ),
    ]
    if len(candidate_coordinates) >= 2:
        layers.append(
            pdk.Layer(
                "PathLayer",
                data=[
                    {
                        "path": candidate_coordinates,
                        "layer_name": "Official Ranked Candidate",
                    }
                ],
                get_path="path",
                get_color=[
                    34,
                    197,
                    94,
                    230,
                ],
                width_min_pixels=4,
                pickable=True,
            )
        )

    actual_data = _valid_position_dataframe(actual_track)
    if not actual_data.empty:
        actual_path = actual_data[
            [
                "lon",
                "lat",
            ]
        ].values.tolist()
        layers.append(
            pdk.Layer(
                "PathLayer",
                data=[
                    {
                        "path": actual_path,
                        "layer_name": "Actual AIS Track",
                    }
                ],
                get_path="path",
                get_color=[
                    14,
                    165,
                    233,
                    230,
                ],
                width_min_pixels=4,
                pickable=True,
            )
        )

    st.pydeck_chart(
        pdk.Deck(
            map_style=None,
            initial_view_state=pdk.ViewState(
                latitude=float(first_lat),
                longitude=float(first_lon),
                zoom=4,
                pitch=0,
            ),
            layers=layers,
            tooltip={
                "text": "Layer: {layer_name}\nMMSI: {mmsi}\nObserved: {observed_at}"
            },
        )
    )
    st.caption(
        "Legend: Current Predicted Route = amber | "
        "Official Ranked Candidate = green | Actual AIS Track = blue | "
        "JWLA = red polygon"
    )


def render_route_candidate_comparison(vessel):
    st.subheader("G. Route Candidate Comparison")

    if not vessel or not vessel.get("mmsi"):
        st.info("Search a vessel with MMSI to compare route candidates.")
        return

    try:
        comparison = compare_route_candidates(vessel.get("mmsi"))
    except Exception as exc:
        st.error(f"Route candidate comparison failed: {exc}")
        return

    if comparison.get("status") != "estimated":
        st.info("Route candidate comparison unavailable.")
        return

    current_metrics = comparison.get("current_metrics") or {}
    candidate_metrics = comparison.get("official_candidate_metrics") or {}
    poc_metrics = comparison.get("poc_candidate_metrics") or {}
    improvement = comparison.get("official_improvement") or {}
    poc_improvement = comparison.get("poc_improvement") or {}
    candidate = comparison.get("official_routeing_candidate") or {}
    source = comparison.get("official_shipping_lane_reference") or {}
    routeing_scores = comparison.get("routeing_scores") or {}
    baseline_score = routeing_scores.get("baseline") or {}
    poc_score = routeing_scores.get("poc_shipping_lane_prior") or {}
    official_ranked = comparison.get("official_ranked_candidate") or {}
    if improvement.get("candidate_performs_better"):
        st.success("Official candidate performs better")
    else:
        st.info("Official candidate does not currently outperform baseline")

    col_source, col_version, col_official = st.columns(3)
    col_base_score, col_poc_score, col_ranked = st.columns(3)
    col_lane_overlap, col_rec_prox, col_ranked_method = st.columns(3)
    col_base_mean, col_poc_mean, col_official_mean = st.columns(3)
    col_base_max, col_poc_max, col_official_max = st.columns(3)
    col_poc_improve, col_official_improve, col_adherence = st.columns(3)
    col_source.metric(
        "Route Prior Source",
        source.get("source") or "-",
    )
    col_version.metric(
        "Source Version",
        source.get("source_version") or "-",
    )
    col_official.metric(
        "Official Reference",
        "YES" if source.get("official") else "NO",
    )
    col_base_score.metric(
        "Baseline Routeing Score",
        _format_number(
            baseline_score.get("routeing_score"),
            decimals=1,
        ),
    )
    col_poc_score.metric(
        "POC Routeing Score",
        _format_number(
            poc_score.get("routeing_score"),
            decimals=1,
        ),
    )
    col_ranked.metric(
        "Official Ranked Candidate",
        official_ranked.get("candidate_id") or "-",
    )
    col_lane_overlap.metric(
        "Official Traffic Lane Overlap",
        _format_number(
            poc_score.get("traffic_lane_overlap_distance_nm"),
            suffix=" nm",
        ),
    )
    col_rec_prox.metric(
        "Recommended Track Proximity",
        _format_number(
            poc_score.get("recommended_track_proximity_nm"),
            suffix=" nm",
        ),
    )
    col_ranked_method.metric(
        "Ranked Candidate Method",
        official_ranked.get("route_method") or "-",
    )
    col_base_mean.metric(
        "Current Mean Deviation",
        _format_number(
            current_metrics.get("mean_deviation_nm"),
            suffix=" nm",
        ),
    )
    col_poc_mean.metric(
        "POC Mean Deviation",
        _format_number(
            poc_metrics.get("mean_deviation_nm"),
            suffix=" nm",
        ),
    )
    col_official_mean.metric(
        "Official Mean Deviation",
        _format_number(
            candidate_metrics.get("mean_deviation_nm"),
            suffix=" nm",
        ),
    )
    col_base_max.metric(
        "Current Max Deviation",
        _format_number(
            current_metrics.get("max_deviation_nm"),
            suffix=" nm",
        ),
    )
    col_poc_max.metric(
        "POC Max Deviation",
        _format_number(
            poc_metrics.get("max_deviation_nm"),
            suffix=" nm",
        ),
    )
    col_official_max.metric(
        "Official Max Deviation",
        _format_number(
            candidate_metrics.get("max_deviation_nm"),
            suffix=" nm",
        ),
    )
    col_poc_improve.metric(
        "POC Mean Improvement",
        _format_number(
            poc_improvement.get("mean_deviation_improvement_nm"),
            suffix=" nm",
        ),
    )
    col_official_improve.metric(
        "Official Mean Improvement",
        _format_number(
            improvement.get("mean_deviation_improvement_nm"),
            suffix=" nm",
        ),
    )
    col_adherence.metric(
        "Official Adherence Improvement",
        _format_number(
            improvement.get("adherence_improvement"),
            decimals=3,
        ),
    )
    st.caption(
        "Candidate method: "
        f"{candidate.get('route_method') or '-'} | "
        "For insurance risk analysis only. Not for vessel navigation. | "
        "This comparison does not activate or persist a new route version."
    )
    show_official_measures = st.checkbox(
        "Show Official Routeing Measures",
        value=False,
    )
    _candidate_comparison_chart(
        comparison,
        show_official_measures=show_official_measures,
    )


def _observed_time_options(track_points):
    return [
        str(point.get("observed_at"))
        for point in track_points
        if point.get("observed_at")
    ]


def render_historical_track_playback(vessel, eta_result=None):
    st.subheader("H. Historical Track Playback")

    if not vessel or not vessel.get("mmsi"):
        st.info("Search a vessel with MMSI to play historical track.")
        return

    mmsi = vessel.get("mmsi")
    col_limit, col_reset = st.columns(
        [
            1,
            1,
        ]
    )
    limit = col_limit.number_input(
        "Track point limit",
        min_value=10,
        max_value=2000,
        value=500,
        step=10,
    )

    state_key = f"track_index_{mmsi}"
    playing_key = f"track_playing_{mmsi}"
    if col_reset.button("Reset Playback"):
        st.session_state[state_key] = 0
        st.session_state[playing_key] = False

    try:
        track_points = get_vessel_track(
            mmsi,
            limit=limit,
        )
    except Exception as exc:
        st.error(f"Track query failed: {exc}")
        return

    if not track_points:
        st.info("No historical track points found in Supabase.")
        return

    time_options = _observed_time_options(track_points)
    if not time_options:
        st.info("No observed_at values available for playback.")
        return

    if state_key not in st.session_state:
        st.session_state[state_key] = len(time_options) - 1
    if playing_key not in st.session_state:
        st.session_state[playing_key] = False

    st.session_state[state_key] = max(
        0,
        min(
            st.session_state[state_key],
            len(time_options) - 1,
        ),
    )

    col_slider, col_play, col_pause = st.columns(
        [
            5,
            1,
            1,
        ]
    )
    selected_index = col_slider.slider(
        "Track Time",
        min_value=0,
        max_value=len(time_options) - 1,
        value=st.session_state[state_key],
        format="%d",
    )
    st.session_state[state_key] = selected_index

    if col_play.button("Play"):
        st.session_state[playing_key] = True
    if col_pause.button("Pause"):
        st.session_state[playing_key] = False

    st.caption(
        f"Selected observed_at: {time_options[st.session_state[state_key]]}"
    )

    visible_track_points = track_points[: st.session_state[state_key] + 1]
    _track_chart(
        visible_track_points,
        current_index=len(visible_track_points) - 1,
        eta_result=eta_result,
    )

    dataframe = _to_dataframe(track_points)
    visible_columns = [
        "mmsi",
        "latitude",
        "longitude",
        "sog",
        "cog",
        "heading",
        "destination",
        "nav_status",
        "observed_at",
    ]
    st.dataframe(
        dataframe[
            [
                column
                for column in visible_columns
                if column in dataframe.columns
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    if (
        st.session_state[playing_key]
        and st.session_state[state_key] < len(time_options) - 1
    ):
        time.sleep(0.8)
        st.session_state[state_key] += 1
        st.rerun()

    if st.session_state[state_key] >= len(time_options) - 1:
        st.session_state[playing_key] = False


def render_collection_status():
    st.subheader("I. Collection Status")

    try:
        latest_run = get_latest_collection_run()
    except Exception as exc:
        st.error(f"Collection status query failed: {exc}")
        return

    if not latest_run:
        st.info("No collection run records available.")
        return

    _display_metrics(
        latest_run,
        [
            ("Latest Status", "status"),
            ("Started At", "started_at"),
            ("Finished At", "finished_at"),
            ("Success Count", "success_count"),
            ("Failed Count", "failed_count"),
        ],
    )


def main():
    st.title("Vessel Risk Monitor Dashboard")

    vessel = render_vessel_search()
    rolling_route_result = _get_rolling_route_result(vessel)
    eta_result = None
    if rolling_route_result:
        eta_result = rolling_route_result.get("eta_result")
    if eta_result is None:
        eta_result = _get_eta_result(vessel)
    render_tracking_control(vessel)
    render_current_position(vessel, eta_result=eta_result)
    render_eta_estimate(vessel, eta_result=eta_result)
    render_route_monitoring_status(vessel, rolling_route_result=rolling_route_result)
    render_route_prediction_history(vessel)
    render_route_candidate_comparison(vessel)
    render_historical_track_playback(vessel, eta_result=eta_result)
    render_collection_status()


if __name__ == "__main__":
    main()

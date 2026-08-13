from unittest.mock import Mock, patch

import risk_monitor.vessel_dashboard as vessel_dashboard


COLUMNS_MOCK_INDEX = 5
PYDECK_MOCK_INDEX = 6
CAPTION_MOCK_INDEX = 7


def _patch_streamlit():
    patches = [
        patch.object(vessel_dashboard.st, "subheader"),
        patch.object(vessel_dashboard.st, "info"),
        patch.object(vessel_dashboard.st, "warning"),
        patch.object(vessel_dashboard.st, "metric"),
        patch.object(vessel_dashboard.st, "dataframe"),
        patch.object(vessel_dashboard.st, "columns"),
        patch.object(vessel_dashboard.st, "pydeck_chart"),
        patch.object(vessel_dashboard.st, "caption"),
    ]
    started = [item.start() for item in patches]
    columns_mock = started[COLUMNS_MOCK_INDEX]
    columns_mock.all_columns = []

    def _columns_side_effect(count):
        columns = [
            Mock()
            for _ in range(count if isinstance(count, int) else len(count))
        ]
        columns_mock.last_columns = columns
        columns_mock.all_columns.append(columns)
        return columns

    columns_mock.side_effect = _columns_side_effect
    return patches, started


def _stop_patches(patches):
    for item in reversed(patches):
        item.stop()


def test_vessel_clear():
    patches, mocks = _patch_streamlit()
    try:
        with patch.object(
            vessel_dashboard,
            "get_vessel_current_risk",
            return_value=[],
        ):
            vessel_dashboard.render_risk_status(
                {
                    "mmsi": "413123456",
                    "latitude": 23.0,
                    "longitude": 117.0,
                    "observed_at": "2026-08-12T00:00:00Z",
                }
            )
        columns_mock = mocks[COLUMNS_MOCK_INDEX]
        assert columns_mock.last_columns[0].metric.call_args.args == (
            "JWLA Risk Status",
            "CLEAR",
        )
        assert columns_mock.last_columns[1].metric.call_args.args == (
            "Current Listed Area",
            "None",
        )
    finally:
        _stop_patches(patches)


def test_vessel_inside_one_zone():
    patches, mocks = _patch_streamlit()
    try:
        with patch.object(
            vessel_dashboard,
            "get_vessel_current_risk",
            return_value=[
                {
                    "zone_name": "JWLA-033 Listed Areas Baseline",
                    "zone_type": "maritime",
                    "source_document": "JWLA-033",
                    "effective_date": "2026-08-12",
                    "observed_at": "2026-08-12T00:00:00Z",
                }
            ],
        ):
            vessel_dashboard.render_risk_status(
                {
                    "mmsi": "413123456",
                    "latitude": 23.0,
                    "longitude": 117.0,
                    "observed_at": "2026-08-12T00:00:00Z",
                }
            )
        warning_mock = mocks[2]
        dataframe_mock = mocks[4]
        warning_mock.assert_called_with("JWLA Risk Status: IN LISTED AREA")
        dataframe = dataframe_mock.call_args.args[0]
        assert len(dataframe) == 1
        assert dataframe.iloc[0]["source"] == "JWLA"
    finally:
        _stop_patches(patches)


def test_vessel_inside_multiple_zones():
    patches, mocks = _patch_streamlit()
    try:
        with patch.object(
            vessel_dashboard,
            "get_vessel_current_risk",
            return_value=[
                {
                    "zone_name": "Zone A",
                    "zone_type": "maritime",
                    "source": "JWLA",
                    "source_document": "JWLA-033",
                    "observed_at": "2026-08-12T00:00:00Z",
                },
                {
                    "zone_name": "Zone B",
                    "zone_type": "maritime",
                    "source": "JWLA",
                    "source_document": "JWLA-033",
                    "observed_at": "2026-08-12T00:00:00Z",
                },
            ],
        ):
            vessel_dashboard.render_risk_status(
                {
                    "mmsi": "413123456",
                    "latitude": 23.0,
                    "longitude": 117.0,
                    "observed_at": "2026-08-12T00:00:00Z",
                }
            )
        dataframe = mocks[4].call_args.args[0]
        assert len(dataframe) == 2
    finally:
        _stop_patches(patches)


def test_risk_rpc_error():
    patches, mocks = _patch_streamlit()
    try:
        with patch.object(
            vessel_dashboard,
            "get_vessel_current_risk",
            side_effect=RuntimeError("rpc failed"),
        ):
            vessel_dashboard.render_risk_status(
                {
                    "mmsi": "413123456",
                    "latitude": 23.0,
                    "longitude": 117.0,
                    "observed_at": "2026-08-12T00:00:00Z",
                }
            )
        mocks[2].assert_called_with("Risk status unavailable: rpc failed")
    finally:
        _stop_patches(patches)


def test_unknown_mmsi():
    patches, mocks = _patch_streamlit()
    try:
        vessel_dashboard.render_risk_status(
            {
                "latitude": 23.0,
                "longitude": 117.0,
                "observed_at": "2026-08-12T00:00:00Z",
            }
        )
        mocks[2].assert_called_with("Risk status unavailable: vessel has no MMSI.")
    finally:
        _stop_patches(patches)


def test_no_latest_position():
    patches, mocks = _patch_streamlit()
    try:
        vessel_dashboard.render_risk_status(
            {
                "mmsi": "413123456",
            }
        )
        mocks[1].assert_called_with(
            "Risk status unavailable: no latest position available."
        )
    finally:
        _stop_patches(patches)


def _multipolygon_zone():
    return {
        "zone_id": "zone-1",
        "zone_version_id": "version-1",
        "zone_name": "JWLA-033 Listed Areas Baseline",
        "zone_type": "maritime",
        "source": "JWLA",
        "source_document": "JWLA-033",
        "effective_date": "2026-08-12",
        "geometry_geojson": {
            "type": "MultiPolygon",
            "coordinates": [
                [
                    [
                        [116.0, 22.0],
                        [118.0, 22.0],
                        [118.0, 24.0],
                        [116.0, 24.0],
                        [116.0, 22.0],
                    ]
                ]
            ],
        },
    }


def test_active_multipolygon_layer_visible_with_clear_status():
    patches, mocks = _patch_streamlit()
    try:
        with patch.object(
            vessel_dashboard,
            "get_active_risk_zones_geojson",
            return_value=[_multipolygon_zone()],
        ), patch.object(
            vessel_dashboard,
            "get_vessel_current_risk",
            return_value=[],
        ):
            vessel = {
                "mmsi": "413123456",
                "latitude": 23.0,
                "longitude": 117.0,
                "observed_at": "2026-08-12T00:00:00Z",
            }
            vessel_dashboard._single_position_chart(vessel)
            vessel_dashboard.render_risk_status(vessel)

        deck = mocks[PYDECK_MOCK_INDEX].call_args.args[0]
        assert deck.layers[0].__class__.__name__ == "Layer"
        assert deck.layers[0].type == "GeoJsonLayer"
        assert mocks[COLUMNS_MOCK_INDEX].last_columns[0].metric.call_args.args == (
            "JWLA Risk Status",
            "CLEAR",
        )
    finally:
        _stop_patches(patches)


def test_no_active_zone_keeps_vessel_marker():
    patches, mocks = _patch_streamlit()
    try:
        with patch.object(
            vessel_dashboard,
            "get_active_risk_zones_geojson",
            return_value=[],
        ):
            vessel_dashboard._single_position_chart(
                {
                    "mmsi": "413123456",
                    "latitude": 23.0,
                    "longitude": 117.0,
                    "observed_at": "2026-08-12T00:00:00Z",
                }
            )

        deck = mocks[PYDECK_MOCK_INDEX].call_args.args[0]
        assert len(deck.layers) == 1
        assert deck.layers[0].type == "ScatterplotLayer"
    finally:
        _stop_patches(patches)


def test_risk_zone_rpc_error_keeps_vessel_marker():
    patches, mocks = _patch_streamlit()
    try:
        with patch.object(
            vessel_dashboard,
            "get_active_risk_zones_geojson",
            side_effect=RuntimeError("rpc failed"),
        ):
            vessel_dashboard._single_position_chart(
                {
                    "mmsi": "413123456",
                    "latitude": 23.0,
                    "longitude": 117.0,
                    "observed_at": "2026-08-12T00:00:00Z",
                }
            )

        mocks[1].assert_called_with("Risk zone layer unavailable")
        deck = mocks[PYDECK_MOCK_INDEX].call_args.args[0]
        assert len(deck.layers) == 1
        assert deck.layers[0].type == "ScatterplotLayer"
    finally:
        _stop_patches(patches)


def test_inside_status_preserved_with_polygon_visible():
    patches, mocks = _patch_streamlit()
    try:
        with patch.object(
            vessel_dashboard,
            "get_active_risk_zones_geojson",
            return_value=[_multipolygon_zone()],
        ), patch.object(
            vessel_dashboard,
            "get_vessel_current_risk",
            return_value=[
                {
                    "zone_name": "JWLA-033 Listed Areas Baseline",
                    "zone_type": "maritime",
                    "source": "JWLA",
                    "source_document": "JWLA-033",
                    "observed_at": "2026-08-12T00:00:00Z",
                }
            ],
        ):
            vessel = {
                "mmsi": "413123456",
                "latitude": 23.0,
                "longitude": 117.0,
                "observed_at": "2026-08-12T00:00:00Z",
            }
            vessel_dashboard._single_position_chart(vessel)
            vessel_dashboard.render_risk_status(vessel)

        deck = mocks[PYDECK_MOCK_INDEX].call_args.args[0]
        assert deck.layers[0].type == "GeoJsonLayer"
        mocks[2].assert_called_with("JWLA Risk Status: IN LISTED AREA")
    finally:
        _stop_patches(patches)


def test_historical_track_and_risk_polygon_layers_visible():
    patches, mocks = _patch_streamlit()
    try:
        with patch.object(
            vessel_dashboard,
            "get_active_risk_zones_geojson",
            return_value=[_multipolygon_zone()],
        ):
            vessel_dashboard._track_chart(
                [
                    {
                        "mmsi": "413123456",
                        "latitude": 23.0,
                        "longitude": 117.0,
                        "observed_at": "2026-08-12T00:00:00Z",
                    },
                    {
                        "mmsi": "413123456",
                        "latitude": 23.2,
                        "longitude": 117.2,
                        "observed_at": "2026-08-12T00:10:00Z",
                    },
                ],
                current_index=1,
            )

        deck = mocks[PYDECK_MOCK_INDEX].call_args.args[0]
        layer_types = [layer.type for layer in deck.layers]
        assert layer_types[0] == "GeoJsonLayer"
        assert "PathLayer" in layer_types
        assert layer_types.count("ScatterplotLayer") == 2
    finally:
        _stop_patches(patches)


def _eta_result(
    distance_method="navigable_route_baseline",
    route_geojson="default",
    warnings=None,
    status="estimated",
):
    if route_geojson == "default":
        route_geojson = {
            "type": "LineString",
            "coordinates": [
                [117.0, 23.0],
                [118.0, 24.0],
                [119.0, 25.0],
            ],
        }
    return {
        "status": status,
        "destination_raw": "CN LYG",
        "destination_normalized": "Lianyungang",
        "destination_unlocode": "CNLYG",
        "destination_latitude": 34.5967,
        "destination_longitude": 119.2214,
        "remaining_distance_nm": 607.6,
        "great_circle_distance_nm": 501.0,
        "navigable_distance_nm": 607.6,
        "route_distance_ratio": 1.213,
        "distance_method": distance_method,
        "route_method": "land_avoidance_baseline",
        "estimated_speed_knots": 11.1,
        "estimated_remaining_hours": 54.7,
        "baseline_estimated_eta": "2026-08-15T21:50:52+00:00",
        "reported_ais_eta": "2026-08-15T11:00:00+00:00",
        "eta_difference_hours": 10.8,
        "confidence": "high",
        "warnings": warnings or [],
        "estimated_route_geojson": route_geojson,
    }


def test_estimated_route_displayed():
    patches, mocks = _patch_streamlit()
    try:
        with patch.object(
            vessel_dashboard,
            "get_active_risk_zones_geojson",
            return_value=[],
        ):
            vessel_dashboard._single_position_chart(
                {
                    "mmsi": "477222100",
                    "latitude": 23.0,
                    "longitude": 117.0,
                    "observed_at": "2026-08-13T00:00:00Z",
                },
                eta_result=_eta_result(),
            )

        deck = mocks[PYDECK_MOCK_INDEX].call_args.args[0]
        assert [layer.type for layer in deck.layers] == [
            "PathLayer",
            "ScatterplotLayer",
            "ScatterplotLayer",
        ]
    finally:
        _stop_patches(patches)


def test_destination_marker_displayed():
    patches, mocks = _patch_streamlit()
    try:
        with patch.object(
            vessel_dashboard,
            "get_active_risk_zones_geojson",
            return_value=[],
        ):
            vessel_dashboard._single_position_chart(
                {
                    "mmsi": "477222100",
                    "latitude": 23.0,
                    "longitude": 117.0,
                    "observed_at": "2026-08-13T00:00:00Z",
                },
                eta_result=_eta_result(),
            )

        deck = mocks[PYDECK_MOCK_INDEX].call_args.args[0]
        destination_layer = deck.layers[1]
        assert destination_layer.type == "ScatterplotLayer"
    finally:
        _stop_patches(patches)


def test_historical_and_estimated_route_coexist():
    patches, mocks = _patch_streamlit()
    try:
        with patch.object(
            vessel_dashboard,
            "get_active_risk_zones_geojson",
            return_value=[],
        ):
            vessel_dashboard._track_chart(
                [
                    {
                        "mmsi": "477222100",
                        "latitude": 23.0,
                        "longitude": 117.0,
                        "observed_at": "2026-08-13T00:00:00Z",
                    },
                    {
                        "mmsi": "477222100",
                        "latitude": 24.0,
                        "longitude": 118.0,
                        "observed_at": "2026-08-13T01:00:00Z",
                    },
                ],
                current_index=1,
                eta_result=_eta_result(),
            )

        deck = mocks[PYDECK_MOCK_INDEX].call_args.args[0]
        assert [layer.type for layer in deck.layers].count("PathLayer") == 2
    finally:
        _stop_patches(patches)


def test_jwla_and_estimated_route_coexist():
    patches, mocks = _patch_streamlit()
    try:
        with patch.object(
            vessel_dashboard,
            "get_active_risk_zones_geojson",
            return_value=[_multipolygon_zone()],
        ):
            vessel_dashboard._single_position_chart(
                {
                    "mmsi": "477222100",
                    "latitude": 23.0,
                    "longitude": 117.0,
                    "observed_at": "2026-08-13T00:00:00Z",
                },
                eta_result=_eta_result(),
            )

        deck = mocks[PYDECK_MOCK_INDEX].call_args.args[0]
        assert [layer.type for layer in deck.layers][:2] == [
            "GeoJsonLayer",
            "PathLayer",
        ]
    finally:
        _stop_patches(patches)


def test_no_route_keeps_dashboard_stable():
    patches, mocks = _patch_streamlit()
    try:
        with patch.object(
            vessel_dashboard,
            "get_active_risk_zones_geojson",
            return_value=[],
        ):
            vessel_dashboard._single_position_chart(
                {
                    "mmsi": "477222100",
                    "latitude": 23.0,
                    "longitude": 117.0,
                    "observed_at": "2026-08-13T00:00:00Z",
                },
                eta_result=_eta_result(route_geojson=None),
            )

        deck = mocks[PYDECK_MOCK_INDEX].call_args.args[0]
        assert [layer.type for layer in deck.layers] == [
            "ScatterplotLayer",
            "ScatterplotLayer",
        ]
    finally:
        _stop_patches(patches)


def test_fallback_great_circle_warning():
    patches, mocks = _patch_streamlit()
    try:
        vessel_dashboard.render_eta_estimate(
            {"mmsi": "477222100"},
            eta_result=_eta_result(
                distance_method="great_circle_baseline",
                warnings=["navigable_route_unavailable"],
            ),
        )

        captions = [
            call.args[0]
            for call in mocks[CAPTION_MOCK_INDEX].call_args_list
        ]
        assert any(
            "Navigable route estimate unavailable" in caption
            for caption in captions
        )
    finally:
        _stop_patches(patches)


def test_destination_unresolved_eta_unavailable():
    patches, mocks = _patch_streamlit()
    try:
        vessel_dashboard.render_eta_estimate(
            {"mmsi": "477222100"},
            eta_result={
                "status": "unavailable",
                "destination_raw": "UNKNOWN",
                "warnings": ["destination_unresolved"],
            },
        )

        mocks[1].assert_called_with(
            "ETA unavailable: Destination could not be resolved to a verified port."
        )
    finally:
        _stop_patches(patches)


def test_route_warnings_user_friendly():
    messages = vessel_dashboard._user_friendly_eta_warnings(
        ["regional_corridor:east_china_to_lianyungang"]
    )

    assert messages == [
        "Estimated route uses a regional baseline maritime corridor."
    ]


def test_eta_information_panel():
    patches, mocks = _patch_streamlit()
    try:
        vessel_dashboard.render_eta_estimate(
            {"mmsi": "477222100"},
            eta_result=_eta_result(),
        )

        metric_calls = []
        for columns in mocks[COLUMNS_MOCK_INDEX].all_columns:
            for column in columns:
                metric_calls.extend(
                    call.args[0]
                    for call in column.metric.call_args_list
                )
        assert "Destination" in metric_calls
        assert "Great-circle Distance" in metric_calls
        assert "Navigable Distance" in metric_calls
        assert "Route Ratio" in metric_calls
    finally:
        _stop_patches(patches)


if __name__ == "__main__":
    test_vessel_clear()
    test_vessel_inside_one_zone()
    test_vessel_inside_multiple_zones()
    test_risk_rpc_error()
    test_unknown_mmsi()
    test_no_latest_position()
    test_active_multipolygon_layer_visible_with_clear_status()
    test_no_active_zone_keeps_vessel_marker()
    test_risk_zone_rpc_error_keeps_vessel_marker()
    test_inside_status_preserved_with_polygon_visible()
    test_historical_track_and_risk_polygon_layers_visible()
    test_estimated_route_displayed()
    test_destination_marker_displayed()
    test_historical_and_estimated_route_coexist()
    test_jwla_and_estimated_route_coexist()
    test_no_route_keeps_dashboard_stable()
    test_fallback_great_circle_warning()
    test_destination_unresolved_eta_unavailable()
    test_route_warnings_user_friendly()
    test_eta_information_panel()
    print("test_vessel_dashboard_risk_status.py passed")

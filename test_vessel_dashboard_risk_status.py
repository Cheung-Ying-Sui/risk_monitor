from unittest.mock import Mock, patch

import vessel_dashboard


def _patch_streamlit():
    patches = [
        patch.object(vessel_dashboard.st, "subheader"),
        patch.object(vessel_dashboard.st, "info"),
        patch.object(vessel_dashboard.st, "warning"),
        patch.object(vessel_dashboard.st, "metric"),
        patch.object(vessel_dashboard.st, "dataframe"),
        patch.object(vessel_dashboard.st, "columns"),
        patch.object(vessel_dashboard.st, "pydeck_chart"),
    ]
    started = [item.start() for item in patches]
    started[-2].return_value = [Mock(), Mock()]
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
        columns_mock = mocks[-2]
        assert columns_mock.return_value[0].metric.call_args.args == (
            "JWLA Risk Status",
            "CLEAR",
        )
        assert columns_mock.return_value[1].metric.call_args.args == (
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

        deck = mocks[-1].call_args.args[0]
        assert deck.layers[0].__class__.__name__ == "Layer"
        assert deck.layers[0].type == "GeoJsonLayer"
        assert mocks[-2].return_value[0].metric.call_args.args == (
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

        deck = mocks[-1].call_args.args[0]
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
        deck = mocks[-1].call_args.args[0]
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

        deck = mocks[-1].call_args.args[0]
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

        deck = mocks[-1].call_args.args[0]
        layer_types = [layer.type for layer in deck.layers]
        assert layer_types[0] == "GeoJsonLayer"
        assert "PathLayer" in layer_types
        assert layer_types.count("ScatterplotLayer") == 2
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
    print("test_vessel_dashboard_risk_status.py passed")

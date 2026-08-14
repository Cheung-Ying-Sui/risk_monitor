import json
from pathlib import Path
from tempfile import TemporaryDirectory

from risk_monitor.navigation.routeing_feature_adapter import (
    adapt_routeing_features_for_prior,
)
from risk_monitor.navigation.shipping_lane_provider import (
    load_official_routeing_reference,
    load_poc_shipping_lane_reference,
)
from scripts.import_navigation_reference import (
    build_processed_reference,
    write_outputs,
)


def _feature(geometry, properties=None):
    return {
        "type": "Feature",
        "properties": {
            "fid": 1,
            "globalid": "{feature-1}",
            "feature_ty": "Recommended Routes",
            "inform": "Test route",
            "orient": 90,
            **(properties or {}),
        },
        "geometry": geometry,
    }


def _write_raw(raw_dir, features_by_kind):
    raw_dir.mkdir(parents=True, exist_ok=True)
    for kind, file_name in {
        "points": "ukho_routeing_measures_points.geojson",
        "lines": "ukho_routeing_measures_lines.geojson",
        "areas": "ukho_routeing_measures_areas.geojson",
    }.items():
        (raw_dir / file_name).write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": features_by_kind.get(kind, []),
                }
            ),
            encoding="utf-8",
        )


def test_raw_source_parse_and_feature_normalization():
    with TemporaryDirectory() as directory:
        raw_dir = Path(directory) / "raw"
        _write_raw(
            raw_dir,
            {
                "lines": [
                    _feature(
                        {
                            "type": "LineString",
                            "coordinates": [[-4, 49], [-3, 49.5]],
                        }
                    )
                ]
            },
        )

        processed = build_processed_reference(raw_dir=raw_dir)

    assert len(processed["features"]) == 1
    properties = processed["features"][0]["properties"]
    assert properties["routeing_type"] == "recommended_track"
    assert properties["official"] is True
    assert properties["source_id"] == "ukho_routeing_measures"


def test_invalid_geometry_rejected():
    with TemporaryDirectory() as directory:
        raw_dir = Path(directory) / "raw"
        _write_raw(
            raw_dir,
            {
                "lines": [
                    _feature(
                        {
                            "type": "LineString",
                            "coordinates": [],
                        }
                    )
                ]
            },
        )

        try:
            build_processed_reference(raw_dir=raw_dir)
        except ValueError as exc:
            assert "invalid or empty geometry" in str(exc)
        else:
            raise AssertionError("invalid geometry should fail")


def test_polygon_line_and_point_measures_preserved():
    with TemporaryDirectory() as directory:
        raw_dir = Path(directory) / "raw"
        _write_raw(
            raw_dir,
            {
                "points": [
                    _feature(
                        {
                            "type": "Point",
                            "coordinates": [-3, 49],
                        }
                    )
                ],
                "lines": [
                    _feature(
                        {
                            "type": "LineString",
                            "coordinates": [[-4, 49], [-3, 49.5]],
                        }
                    )
                ],
                "areas": [
                    _feature(
                        {
                            "type": "Polygon",
                            "coordinates": [[[-4, 49], [-3, 49], [-3, 50], [-4, 49]]],
                        },
                        properties={
                            "feature_ty": "Traffic Separation Scheme Lanes",
                        },
                    )
                ],
            },
        )

        processed = build_processed_reference(raw_dir=raw_dir)

    kinds = {feature["properties"]["geometry_kind"] for feature in processed["features"]}
    assert kinds == {"point", "line", "area"}


def test_duplicate_feature_ids_handled():
    with TemporaryDirectory() as directory:
        raw_dir = Path(directory) / "raw"
        duplicate = _feature(
            {
                "type": "LineString",
                "coordinates": [[-4, 49], [-3, 49.5]],
            }
        )
        _write_raw(raw_dir, {"lines": [duplicate, duplicate]})

        processed = build_processed_reference(raw_dir=raw_dir)

    ids = [feature["id"] for feature in processed["features"]]
    assert len(ids) == len(set(ids))


def test_source_manifest_written():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        raw_dir = root / "raw"
        processed_dir = root / "processed"
        manifest = root / "source_manifest.json"
        _write_raw(
            raw_dir,
            {
                "lines": [
                    _feature(
                        {
                            "type": "LineString",
                            "coordinates": [[-4, 49], [-3, 49.5]],
                        }
                    )
                ]
            },
        )

        result = write_outputs(
            raw_dir=raw_dir,
            processed_dir=processed_dir,
            manifest_path=manifest,
        )

        manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    assert result["feature_count"] == 1
    assert manifest_data["sources"][0]["licence"] == "Open Government Licence v3.0"


def test_missing_metadata_is_not_required_for_raw_feature():
    with TemporaryDirectory() as directory:
        raw_dir = Path(directory) / "raw"
        _write_raw(
            raw_dir,
            {
                "lines": [
                    {
                        "type": "Feature",
                        "properties": {},
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[-4, 49], [-3, 49.5]],
                        },
                    }
                ]
            },
        )

        processed = build_processed_reference(raw_dir=raw_dir)

    assert processed["features"][0]["properties"]["routeing_type"] == "other"


def test_adapter_does_not_convert_polygon_to_centerline():
    features = [
        {
            "id": "area-1",
            "properties": {
                "feature_id": "area-1",
                "routeing_type": "traffic_lane",
                "geometry_kind": "area",
                "official": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-4, 49], [-3, 49], [-3, 50], [-4, 49]]],
            },
        }
    ]

    assert adapt_routeing_features_for_prior(features) == []


def test_line_routeing_measure_adapted():
    features = [
        {
            "id": "line-1",
            "properties": {
                "feature_id": "line-1",
                "routeing_type": "recommended_track",
                "geometry_kind": "line",
                "official": True,
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [[-4, 49], [-3, 49.5]],
            },
        }
    ]

    assert len(adapt_routeing_features_for_prior(features)) == 1


def test_point_routeing_measure_not_adapted_to_waypoint_route():
    features = [
        {
            "id": "point-1",
            "properties": {
                "feature_id": "point-1",
                "routeing_type": "other",
                "geometry_kind": "point",
                "official": True,
            },
            "geometry": {
                "type": "Point",
                "coordinates": [-4, 49],
            },
        }
    ]

    assert adapt_routeing_features_for_prior(features) == []


def test_official_provider_preferred_and_poc_retained():
    official = load_official_routeing_reference()
    poc = load_poc_shipping_lane_reference()

    assert official["official"] is True
    assert official["source"] == "ukho_routeing_measures"
    assert poc["official"] is False


if __name__ == "__main__":
    test_raw_source_parse_and_feature_normalization()
    test_invalid_geometry_rejected()
    test_polygon_line_and_point_measures_preserved()
    test_duplicate_feature_ids_handled()
    test_source_manifest_written()
    test_missing_metadata_is_not_required_for_raw_feature()
    test_adapter_does_not_convert_polygon_to_centerline()
    test_line_routeing_measure_adapted()
    test_point_routeing_measure_not_adapted_to_waypoint_route()
    test_official_provider_preferred_and_poc_retained()
    print("test_navigation_reference_import.py passed")

from unittest.mock import patch

from risk_monitor import rolling_route_repository


ROUTE = {
    "type": "LineString",
    "coordinates": [
        [0, 0],
        [10, 0],
    ],
}

NEW_ROUTE = {
    "type": "LineString",
    "coordinates": [
        [5, 0.5],
        [12, 2],
    ],
}


def _latest(destination="MAPTM", latitude=0, longitude=5, cog=90, position_id=100):
    return {
        "vessel_id": "vessel-1",
        "position_id": position_id,
        "mmsi": "228397600",
        "latitude": latitude,
        "longitude": longitude,
        "sog": 12,
        "cog": cog,
        "destination": destination,
        "observed_at": "2026-08-14T00:00:00+00:00",
    }


def _destination(raw="MAPTM", name="Tanger Med"):
    return {
        "raw_destination": raw,
        "normalized_destination": name,
        "unlocode": raw,
        "latitude": 2,
        "longitude": 12,
        "resolution_status": "resolved",
    }


def _route(version=1, route=ROUTE, destination_raw="MAPTM", origin_position_id=100):
    return {
        "route_prediction_id": f"route-{version}",
        "vessel_id": "vessel-1",
        "mmsi": "228397600",
        "origin_position_id": origin_position_id,
        "destination_raw": destination_raw,
        "destination_normalized": "Tanger Med",
        "destination_unlocode": destination_raw,
        "route_version": version,
        "route_method": "direct_sea_baseline",
        "distance_method": "navigable_route_baseline",
        "route_geojson": route,
        "great_circle_distance_nm": 600,
        "navigable_distance_nm": 600,
        "route_distance_ratio": 1,
        "route_created_at": "2026-08-14T00:00:00+00:00",
        "route_update_reason": "initial_route" if version == 1 else "route_deviation",
        "status": "active",
        "origin": {
            "position_id": origin_position_id,
        },
    }


def _patch_common(
    active_route,
    latest=None,
    destination=None,
    new_points=None,
    created_route=None,
):
    return patch.multiple(
        rolling_route_repository,
        get_latest_position_by_mmsi=lambda _mmsi: latest or _latest(),
        resolve_destination=lambda _raw: destination or _destination(),
        get_active_route_prediction=lambda _mmsi: active_route,
        get_track_points_after_prediction=lambda *_args, **_kwargs: new_points or [],
        create_route_prediction=lambda _snapshot: created_route or _route(),
        _estimate_eta_for_route=lambda *_args, **_kwargs: {
            "status": "estimated",
            "estimated_route_geojson": (
                created_route or active_route or _route()
            )["route_geojson"],
        },
    )


def test_no_route_creates_v1():
    created = _route(version=1, origin_position_id=100)
    with _patch_common(active_route=None, created_route=created):
        result = rolling_route_repository.get_rolling_route_prediction("228397600")

    assert result["route_updated"] is True
    assert result["active_route"]["route_version"] == 1
    assert result["deviation_result"]["status"] == "awaiting_new_ais_position"


def test_persisted_route_reused():
    active = _route(version=1)
    with _patch_common(active_route=active):
        result = rolling_route_repository.get_rolling_route_prediction("228397600")

    assert result["route_updated"] is False
    assert result["active_route"]["route_prediction_id"] == "route-1"


def test_dashboard_refresh_does_not_regenerate_route():
    active = _route(version=1)
    with _patch_common(active_route=active), patch.object(
        rolling_route_repository,
        "estimate_navigable_route",
        side_effect=AssertionError("route engine should not run"),
    ):
        result = rolling_route_repository.get_rolling_route_prediction("228397600")

    assert result["route_updated"] is False


def test_no_ais_after_route_creation():
    active = _route(version=1)
    with _patch_common(active_route=active, new_points=[]):
        result = rolling_route_repository.get_rolling_route_prediction("228397600")

    assert result["new_ais_points_since_prediction"] == 0
    assert result["deviation_result"]["status"] == "awaiting_new_ais_position"


def test_one_new_ais_point_does_not_reroute():
    active = _route(version=1)
    point = _latest(latitude=0.4, longitude=5, position_id=101)
    with _patch_common(active_route=active, new_points=[point]):
        result = rolling_route_repository.get_rolling_route_prediction("228397600")

    assert result["new_ais_points_since_prediction"] == 1
    assert result["deviation_result"]["status"] == "deviating"
    assert result["route_updated"] is False


def test_three_consecutive_deviations_create_v2():
    active = _route(version=1)
    new_route = _route(version=2, route=NEW_ROUTE, origin_position_id=103)
    points = [
        _latest(latitude=0.3, longitude=3, position_id=101),
        _latest(latitude=0.4, longitude=4, position_id=102),
        _latest(latitude=0.5, longitude=5, position_id=103),
    ]
    with _patch_common(
        active_route=active,
        new_points=points,
        created_route=new_route,
        latest=points[-1],
    ):
        result = rolling_route_repository.get_rolling_route_prediction("228397600")

    assert result["route_updated"] is True
    assert result["previous_route"]["route_version"] == 1
    assert result["active_route"]["route_version"] == 2


def test_destination_changed_creates_new_version():
    active = _route(version=1)
    latest = _latest(destination="DEHAM", position_id=104)
    destination = _destination(raw="DEHAM", name="Hamburg")
    new_route = {
        **_route(version=2, route=NEW_ROUTE, destination_raw="DEHAM"),
        "route_update_reason": "destination_changed",
    }
    with _patch_common(
        active_route=active,
        latest=latest,
        destination=destination,
        created_route=new_route,
    ):
        result = rolling_route_repository.get_rolling_route_prediction("228397600")

    assert result["route_updated"] is True
    assert result["active_route"]["route_update_reason"] == "destination_changed"


class _Response:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, rows):
        self.rows = rows
        self.filters = {}

    def select(self, _fields):
        return self

    def eq(self, field, value):
        self.filters[field] = value
        return self

    def order(self, _field, desc=False):
        return self

    def limit(self, _limit):
        return self

    def execute(self):
        rows = self.rows
        for field, value in self.filters.items():
            rows = [row for row in rows if row.get(field) == value]
        return _Response(rows)


class _FakeRpc:
    def __init__(self, store, function_name, params):
        self.store = store
        self.function_name = function_name
        self.params = params

    def execute(self):
        if self.function_name == "get_route_prediction":
            return _Response(
                [
                    row
                    for row in self.store
                    if row["id"] == self.params["p_route_prediction_id"]
                ][:1]
            )

        request_id = self.params["p_request_id"]
        for row in self.store:
            if row.get("request_id") == request_id:
                return _Response(
                    [
                        {
                            "route_prediction_id": row["id"],
                            "route_version": row["route_version"],
                            "old_route_prediction_id": None,
                            "inserted": False,
                        }
                    ]
                )

        old_active = None
        for row in self.store:
            if row["mmsi"] == self.params["p_mmsi"] and row["status"] == "active":
                row["status"] = "superseded"
                row["superseded_at"] = "2026-08-14T00:10:00+00:00"
                old_active = row

        version = max(
            [row["route_version"] for row in self.store if row["mmsi"] == self.params["p_mmsi"]],
            default=0,
        ) + 1
        row = {
            "id": f"route-{version}",
            "vessel_id": self.params["p_vessel_id"],
            "mmsi": self.params["p_mmsi"],
            "origin_position_id": self.params["p_origin_position_id"],
            "destination_raw": self.params["p_destination_raw"],
            "destination_normalized": self.params["p_destination_normalized"],
            "destination_unlocode": self.params["p_destination_unlocode"],
            "route_version": version,
            "route_method": self.params["p_route_method"],
            "route_geojson": self.params["p_route_geojson"],
            "great_circle_distance_nm": self.params["p_great_circle_distance_nm"],
            "navigable_distance_nm": self.params["p_navigable_distance_nm"],
            "route_distance_ratio": self.params["p_route_distance_ratio"],
            "route_created_at": "2026-08-14T00:10:00+00:00",
            "route_update_reason": self.params["p_route_update_reason"],
            "status": "active",
            "superseded_at": None,
            "request_id": request_id,
            "created_at": "2026-08-14T00:10:00+00:00",
        }
        self.store.append(row)
        return _Response(
            [
                {
                    "route_prediction_id": row["id"],
                    "route_version": version,
                    "old_route_prediction_id": old_active["id"] if old_active else None,
                    "inserted": True,
                }
            ]
        )


class _FakeSchema:
    def __init__(self, store):
        self.store = store

    def table(self, _table_name):
        return _FakeQuery(self.store)

    def rpc(self, function_name, params):
        return _FakeRpc(self.store, function_name, params)


class _FakeSupabase:
    def __init__(self, store):
        self.store = store

    def schema(self, _schema_name):
        return _FakeSchema(self.store)


def _route_row(route):
    return {
        "id": route["route_prediction_id"],
        "vessel_id": route["vessel_id"],
        "mmsi": route["mmsi"],
        "origin_position_id": route["origin_position_id"],
        "destination_raw": route["destination_raw"],
        "destination_normalized": route["destination_normalized"],
        "destination_unlocode": route["destination_unlocode"],
        "route_version": route["route_version"],
        "route_method": route["route_method"],
        "route_geojson": route["route_geojson"],
        "great_circle_distance_nm": route["great_circle_distance_nm"],
        "navigable_distance_nm": route["navigable_distance_nm"],
        "route_distance_ratio": route["route_distance_ratio"],
        "route_created_at": route["route_created_at"],
        "route_update_reason": route["route_update_reason"],
        "status": route["status"],
        "superseded_at": None,
        "request_id": route.get("request_id"),
        "created_at": route["route_created_at"],
    }


def test_activation_supersedes_v1_and_preserves_history():
    store = [_route_row(_route(version=1))]
    snapshot = {
        "vessel_id": "vessel-1",
        "mmsi": "228397600",
        "origin_position_id": 103,
        "destination_raw": "MAPTM",
        "destination_normalized": "Tanger Med",
        "destination_unlocode": "MAPTM",
        "route_method": "direct_sea_baseline",
        "route_geojson": NEW_ROUTE,
        "great_circle_distance_nm": 500,
        "navigable_distance_nm": 500,
        "route_distance_ratio": 1,
        "route_update_reason": "route_deviation",
        "request_id": "req-v2",
    }

    with patch.object(rolling_route_repository, "supabase", _FakeSupabase(store)):
        result = rolling_route_repository.create_route_prediction(snapshot)

    assert result["route_version"] == 2
    assert len(store) == 2
    assert len([row for row in store if row["status"] == "active"]) == 1
    assert store[0]["status"] == "superseded"


def test_duplicate_request_idempotency():
    store = []
    snapshot = {
        "vessel_id": "vessel-1",
        "mmsi": "228397600",
        "origin_position_id": 100,
        "destination_raw": "MAPTM",
        "destination_normalized": "Tanger Med",
        "destination_unlocode": "MAPTM",
        "route_method": "direct_sea_baseline",
        "route_geojson": ROUTE,
        "great_circle_distance_nm": 600,
        "navigable_distance_nm": 600,
        "route_distance_ratio": 1,
        "route_update_reason": "initial_route",
        "request_id": "req-v1",
    }

    with patch.object(rolling_route_repository, "supabase", _FakeSupabase(store)):
        first = rolling_route_repository.create_route_prediction(snapshot)
        second = rolling_route_repository.create_route_prediction(snapshot)

    assert first["route_prediction_id"] == second["route_prediction_id"]
    assert len(store) == 1


if __name__ == "__main__":
    test_no_route_creates_v1()
    test_persisted_route_reused()
    test_dashboard_refresh_does_not_regenerate_route()
    test_no_ais_after_route_creation()
    test_one_new_ais_point_does_not_reroute()
    test_three_consecutive_deviations_create_v2()
    test_destination_changed_creates_new_version()
    test_activation_supersedes_v1_and_preserves_history()
    test_duplicate_request_idempotency()
    print("test_rolling_route_repository.py passed")

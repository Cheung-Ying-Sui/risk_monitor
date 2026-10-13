from unittest.mock import patch

from risk_monitor import position_repository


class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self):
        self.payload = None

    def upsert(self, payload, on_conflict=None):
        self.payload = payload
        self.on_conflict = on_conflict
        return self

    def execute(self):
        return _Response([{**self.payload, "id": 123}])


class _Schema:
    def __init__(self):
        self.query = _Query()

    def table(self, table_name):
        assert table_name == "vessel_positions"
        return self.query


class _Supabase:
    def __init__(self):
        self.tracking = _Schema()

    def schema(self, schema_name):
        assert schema_name == "tracking"
        return self.tracking


POSITION = {
    "latitude": 22.3,
    "longitude": 114.1,
    "sog": 12,
    "cog": 90,
    "destination": "SGSIN",
    "observed_at": "2026-09-05T12:00:00Z",
}


def test_successful_position_upsert_triggers_prediction_refresh():
    fake_supabase = _Supabase()
    with patch.object(
        position_repository, "supabase", fake_supabase
    ), patch.object(
        position_repository,
        "get_chinaports_source_id",
        return_value="source-1",
    ), patch.object(
        position_repository,
        "refresh_prediction_after_position",
        return_value={"status": "updated"},
    ) as refresh:
        rows = position_repository.upsert_position_for_vessel(
            "vessel-1",
            "477123456",
            POSITION,
        )

    assert rows[0]["id"] == 123
    refresh.assert_called_once_with(
        vessel_id="vessel-1",
        mmsi="477123456",
        observed_at="2026-09-05T12:00:00Z",
    )


def test_prediction_trigger_failure_does_not_fail_position_upsert():
    fake_supabase = _Supabase()
    with patch.object(
        position_repository, "supabase", fake_supabase
    ), patch.object(
        position_repository,
        "get_chinaports_source_id",
        return_value="source-1",
    ), patch.object(
        position_repository,
        "refresh_prediction_after_position",
        side_effect=RuntimeError("prediction failed"),
    ):
        rows = position_repository.upsert_position_for_vessel(
            "vessel-1",
            "477123456",
            POSITION,
        )

    assert rows[0]["id"] == 123

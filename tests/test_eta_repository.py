from unittest.mock import patch

from risk_monitor import eta_repository


class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, data):
        self.data = data

    def select(self, _fields):
        return self

    def eq(self, _field, _value):
        return self

    def gte(self, _field, _value):
        return self

    def order(self, _field, desc=False):
        return self

    def limit(self, _limit):
        return self

    def execute(self):
        if isinstance(self.data, Exception):
            raise self.data
        return _Response(self.data)


class _Schema:
    def __init__(self, table_data):
        self.table_data = table_data

    def table(self, table_name):
        return _Query(self.table_data[table_name].pop(0))


class _Supabase:
    def __init__(self, table_data):
        self.table_data = table_data

    def schema(self, _schema_name):
        return _Schema(self.table_data)


def test_repository_success():
    supabase = _Supabase(
        {
            "latest_vessel_positions": [
                [
                    {
                        "position_id": 1,
                        "mmsi": "123",
                        "latitude": 1.2644,
                        "longitude": 103.84,
                        "sog": 12,
                        "destination": "Hong Kong",
                    }
                ]
            ],
            "vessel_positions": [
                [{"eta": "08-16 12:00"}],
                [{"sog": 12}, {"sog": 13}, {"sog": 14}],
                [{"sog": 12}, {"sog": 13}, {"sog": 14}],
                [{"sog": 12}, {"sog": 13}, {"sog": 14}],
            ],
        }
    )

    with patch.object(eta_repository, "supabase", supabase), patch.object(
        eta_repository,
        "estimate_navigable_route",
        return_value={
            "status": "estimated",
            "route_method": "direct_sea_baseline",
            "distance_method": "navigable_route_baseline",
            "great_circle_distance_nm": 100,
            "navigable_distance_nm": 100,
            "route_distance_ratio": 1.0,
            "estimated_route_geojson": {
                "type": "LineString",
                "coordinates": [[103.84, 1.2644], [114.1694, 22.3193]],
            },
            "warnings": [],
        },
    ):
        result = eta_repository.get_vessel_eta_estimate("123")

    assert result["status"] == "estimated"
    assert result["destination_normalized"] == "Hong Kong"
    assert result["speed_method"] == "recent_6h_moving_sog_median"


def test_repository_no_latest_position():
    supabase = _Supabase(
        {
            "latest_vessel_positions": [
                [],
            ],
        }
    )

    with patch.object(eta_repository, "supabase", supabase):
        result = eta_repository.get_vessel_eta_estimate("123")

    assert result["status"] == "unavailable"
    assert "no_latest_position" in result["warnings"]


def test_repository_destination_unresolved():
    supabase = _Supabase(
        {
            "latest_vessel_positions": [
                [
                    {
                        "position_id": None,
                        "mmsi": "123",
                        "latitude": 1.2644,
                        "longitude": 103.84,
                        "sog": 12,
                        "destination": "UNKNOWN PORT",
                    }
                ]
            ],
            "vessel_positions": [
                [{"sog": 12}, {"sog": 13}, {"sog": 14}],
                [{"sog": 12}, {"sog": 13}, {"sog": 14}],
                [{"sog": 12}, {"sog": 13}, {"sog": 14}],
            ],
        }
    )

    with patch.object(eta_repository, "supabase", supabase):
        result = eta_repository.get_vessel_eta_estimate("123")

    assert result["status"] == "unavailable"
    assert "destination_unresolved" in result["warnings"]


def test_repository_failure():
    supabase = _Supabase(
        {
            "latest_vessel_positions": [
                RuntimeError("rpc failed"),
            ],
        }
    )

    with patch.object(eta_repository, "supabase", supabase):
        result = eta_repository.get_vessel_eta_estimate("123")

    assert result["status"] == "unavailable"
    assert result["warnings"][0].startswith("repository_failure:")


if __name__ == "__main__":
    test_repository_success()
    test_repository_no_latest_position()
    test_repository_destination_unresolved()
    test_repository_failure()
    print("test_eta_repository.py passed")

import pytest

from risk_monitor.vessel_search_service import (
    ExternalSearchUnsupportedError,
    ExternalSourceUnavailableError,
    VesselConflictError,
    VesselNotFoundError,
    VesselSearchService,
)


class _FakeGateway:
    def __init__(
        self,
        vessels_by_mmsi=None,
        vessels_by_imo=None,
        tracking_by_vessel_id=None,
        latest_by_vessel_id=None,
        external_result=None,
        external_error=None,
        position_error=None,
    ):
        self.vessels_by_mmsi = vessels_by_mmsi or {}
        self.vessels_by_imo = vessels_by_imo or {}
        self.tracking_by_vessel_id = tracking_by_vessel_id or {}
        self.latest_by_vessel_id = latest_by_vessel_id or {}
        self.external_result = external_result
        self.external_error = external_error
        self.position_error = position_error
        self.external_calls = []
        self.upserted_vessels = []
        self.activated_vessels = []
        self.persisted_positions = []

    def get_vessel_by_mmsi(self, mmsi):
        return self.vessels_by_mmsi.get(str(mmsi))

    def get_vessel_by_imo(self, imo):
        return self.vessels_by_imo.get(str(imo))

    def get_latest_position_by_vessel_id(self, vessel_id):
        return self.latest_by_vessel_id.get(str(vessel_id))

    def get_tracking_status_by_vessel_id(self, vessel_id):
        return self.tracking_by_vessel_id.get(str(vessel_id))

    def fetch_external_ship_info(self, mmsi):
        self.external_calls.append(str(mmsi))
        if self.external_error:
            raise self.external_error

        return self.external_result

    def upsert_vessel(self, vessel_data):
        self.upserted_vessels.append(vessel_data)
        vessel = {
            "id": "new-vessel-id",
            "mmsi": vessel_data["mmsi"],
            "imo": vessel_data.get("imo"),
            "ship_name": vessel_data.get("ship_name"),
            "ship_type": vessel_data.get("ship_type"),
            "flag_state": vessel_data.get("flag_state"),
            "callsign": vessel_data.get("callsign"),
        }
        self.vessels_by_mmsi[vessel["mmsi"]] = vessel
        if vessel.get("imo"):
            self.vessels_by_imo[vessel["imo"]] = vessel

        return [vessel]

    def activate_tracking_by_vessel(self, vessel):
        self.activated_vessels.append(vessel)
        tracking = self.tracking_by_vessel_id.get(vessel["id"])
        if tracking:
            tracking["is_active"] = True
            return tracking

        tracking = {
            "vessel_id": vessel["id"],
            "mmsi": vessel["mmsi"],
            "is_active": True,
            "tracking_mode": "history_tracking",
            "priority": 0,
        }
        self.tracking_by_vessel_id[vessel["id"]] = tracking
        return tracking

    def upsert_position_for_vessel(self, vessel_id, mmsi, position_data):
        if self.position_error:
            raise self.position_error

        self.persisted_positions.append(
            {
                "vessel_id": vessel_id,
                "mmsi": mmsi,
                "position_data": position_data,
            }
        )
        return [position_data]


def _local_vessel(vessel_id="vessel-1", mmsi="477123456", imo="9876543"):
    return {
        "id": vessel_id,
        "mmsi": mmsi,
        "imo": imo,
        "ship_name": "PACIFIC TRADER",
        "ship_type": "Cargo",
        "flag_state": "HK",
        "callsign": "VRAB1",
    }


def _external_raw(mmsi=477222100, imo=9632313):
    return {
        "mmsi": mmsi,
        "imo": imo,
        "shipname": "XIN HAI TONG 56",
        "shiptype": 79,
        "shipCountry": "HK",
        "callsign": "VRLP6",
        "length": 189,
        "width": 32,
        "shipAllDun": "32962.0",
        "latitude": "N 34度44.4888分",
        "longitude": "E 119度27.7326分",
        "sog": "0.100000001",
        "cog": "235.600006",
        "trueHeading": 291,
        "navStatus": 5,
        "destination": "CN LYG",
        "timeStamp": "2026-08-16 08:11(UTC+8)",
        "message": "permission text that must not leak",
        "url": "memberService?lang=zh",
    }


def test_local_mmsi_search_does_not_call_external():
    vessel = _local_vessel()
    gateway = _FakeGateway(
        vessels_by_mmsi={"477123456": vessel},
        tracking_by_vessel_id={"vessel-1": {"is_active": True}},
    )
    service = VesselSearchService(gateway)

    result = service.search(mmsi="477123456")

    assert result["source"] == "local"
    assert result["is_persisted"] is True
    assert result["id"] == "vessel-1"
    assert result["is_tracked"] is True
    assert gateway.external_calls == []


def test_local_imo_search_does_not_call_external():
    vessel = _local_vessel()
    gateway = _FakeGateway(vessels_by_imo={"9876543": vessel})
    service = VesselSearchService(gateway)

    result = service.search(imo="9876543")

    assert result["source"] == "local"
    assert result["id"] == "vessel-1"
    assert gateway.external_calls == []


def test_local_miss_external_found_normalizes_candidate_without_raw_fields():
    gateway = _FakeGateway(external_result=_external_raw())
    service = VesselSearchService(gateway)

    result = service.search(mmsi="477222100")

    assert result["source"] == "external"
    assert result["is_persisted"] is False
    assert result["id"] is None
    assert result["mmsi"] == "477222100"
    assert result["imo"] == "9632313"
    assert result["latest_position"]["latitude"] == pytest.approx(34.74148)
    assert "message" not in result
    assert "url" not in result


def test_external_imo_zero_normalizes_to_none():
    gateway = _FakeGateway(external_result=_external_raw(imo=0))
    service = VesselSearchService(gateway)

    result = service.search(mmsi="477222100")

    assert result["imo"] is None


def test_invalid_external_coordinates_return_null_latest_position():
    raw = _external_raw()
    raw["latitude"] = "N 999度44.4888分"
    gateway = _FakeGateway(external_result=raw)
    service = VesselSearchService(gateway)

    result = service.search(mmsi="477222100")

    assert result["latest_position"] is None


def test_external_no_result_returns_not_found():
    gateway = _FakeGateway(external_result={})
    service = VesselSearchService(gateway)

    with pytest.raises(VesselNotFoundError):
        service.search(mmsi="477222100")


def test_external_unavailable_is_distinct_from_not_found():
    gateway = _FakeGateway(
        external_error=ExternalSourceUnavailableError(
            "External vessel source unavailable."
        )
    )
    service = VesselSearchService(gateway)

    with pytest.raises(ExternalSourceUnavailableError):
        service.search(mmsi="477222100")


def test_imo_only_local_miss_queries_chinaports():
    gateway = _FakeGateway(external_result=_external_raw())
    service = VesselSearchService(gateway)

    result = service.search(imo="9632313")
    assert result["mmsi"] == "477222100"
    assert gateway.external_calls == ["9632313"]


def test_onboard_new_external_vessel_persists_tracks_and_position():
    gateway = _FakeGateway()
    service = VesselSearchService(gateway)

    result = service.onboard(
        {
            "source": "chinaports",
            "mmsi": "477222100",
            "imo": "9632313",
            "name": "XIN HAI TONG 56",
            "ship_type": "Cargo",
            "latest_position": {
                "latitude": 34.74148,
                "longitude": 119.46221,
                "observed_at": "2026-08-16T00:11:00+00:00",
            },
        }
    )

    assert result["id"] == "new-vessel-id"
    assert result["is_persisted"] is True
    assert result["is_tracked"] is True
    assert gateway.upserted_vessels
    assert gateway.activated_vessels
    assert gateway.persisted_positions


def test_onboard_without_position_still_persists_and_tracks():
    gateway = _FakeGateway()
    service = VesselSearchService(gateway)

    result = service.onboard(
        {
            "source": "chinaports",
            "mmsi": "477222100",
            "name": "XIN HAI TONG 56",
        }
    )

    assert result["id"] == "new-vessel-id"
    assert result["is_tracked"] is True
    assert gateway.persisted_positions == []


def test_repeated_onboard_reuses_existing_vessel():
    vessel = _local_vessel(vessel_id="existing-id", mmsi="477222100")
    gateway = _FakeGateway(vessels_by_mmsi={"477222100": vessel})
    service = VesselSearchService(gateway)

    result = service.onboard(
        {
            "source": "chinaports",
            "mmsi": "477222100",
            "name": "XIN HAI TONG 56",
        }
    )

    assert result["id"] == "existing-id"
    assert gateway.upserted_vessels == []
    assert result["is_tracked"] is True


def test_onboard_reactivates_inactive_tracking():
    vessel = _local_vessel(vessel_id="existing-id", mmsi="477222100")
    gateway = _FakeGateway(
        vessels_by_mmsi={"477222100": vessel},
        tracking_by_vessel_id={
            "existing-id": {
                "vessel_id": "existing-id",
                "is_active": False,
                "tracking_mode": "high_risk_monitoring",
            }
        },
    )
    service = VesselSearchService(gateway)

    result = service.onboard(
        {
            "source": "chinaports",
            "mmsi": "477222100",
            "name": "XIN HAI TONG 56",
        }
    )

    assert result["is_tracked"] is True
    assert (
        gateway.tracking_by_vessel_id["existing-id"]["tracking_mode"]
        == "high_risk_monitoring"
    )


def test_onboard_active_tracking_is_idempotent():
    vessel = _local_vessel(vessel_id="existing-id", mmsi="477222100")
    gateway = _FakeGateway(
        vessels_by_mmsi={"477222100": vessel},
        tracking_by_vessel_id={
            "existing-id": {
                "vessel_id": "existing-id",
                "is_active": True,
            }
        },
    )
    service = VesselSearchService(gateway)

    result = service.onboard(
        {
            "source": "chinaports",
            "mmsi": "477222100",
            "name": "XIN HAI TONG 56",
        }
    )

    assert result["is_tracked"] is True


def test_onboard_imo_mmsi_conflict_raises_conflict():
    gateway = _FakeGateway(
        vessels_by_imo={
            "9632313": _local_vessel(
                vessel_id="other-id",
                mmsi="111111111",
                imo="9632313",
            )
        }
    )
    service = VesselSearchService(gateway)

    with pytest.raises(VesselConflictError):
        service.onboard(
            {
                "source": "chinaports",
                "mmsi": "477222100",
                "imo": "9632313",
                "name": "XIN HAI TONG 56",
            }
        )


def test_position_failure_returns_warning_without_rollback():
    gateway = _FakeGateway(position_error=RuntimeError("position failed"))
    service = VesselSearchService(gateway)

    result = service.onboard(
        {
            "source": "chinaports",
            "mmsi": "477222100",
            "name": "XIN HAI TONG 56",
            "latest_position": {
                "latitude": 34.74148,
                "longitude": 119.46221,
                "observed_at": "2026-08-16T00:11:00+00:00",
            },
        }
    )

    assert result["is_tracked"] is True
    assert result["warnings"] == ["Latest position persistence failed."]


def test_invalid_onboard_position_returns_warning_without_persistence():
    gateway = _FakeGateway()
    service = VesselSearchService(gateway)

    result = service.onboard(
        {
            "source": "chinaports",
            "mmsi": "477222100",
            "name": "XIN HAI TONG 56",
            "latest_position": {
                "latitude": 999,
                "longitude": 119.46221,
                "observed_at": "2026-08-16T00:11:00+00:00",
            },
        }
    )

    assert result["is_tracked"] is True
    assert result["warnings"] == [
        "Latest position is invalid and was not persisted."
    ]
    assert gateway.persisted_positions == []

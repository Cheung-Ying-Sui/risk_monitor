from datetime import datetime, timedelta, timezone

from risk_monitor.insurance_voyage_lifecycle import ENDED_STATUS, VoyageLifecycleService, next_lifecycle


T0 = datetime(2026, 10, 11, 0, 0, tzinfo=timezone.utc)


def shipment(shipment_id="s1", declaration_id="d1", port="青岛港", extra=None):
    return {"id": shipment_id, "declaration_id": declaration_id, "imo_number": "9127136",
            "discharge_port": port, "etd": "2026-10-10T00:00:00Z", "coverage_status": None,
            "extra_data": extra or {}, "updated_at": "2026-10-11T00:00:00Z"}


def position(observed, *, speed=0.1, nav="moored", latitude=36.033333, longitude=120.266667):
    return {"position_id": str(observed), "observed_at": observed.isoformat(),
            "latitude": latitude, "longitude": longitude, "sog": speed, "nav_status": nav}


def advance(row, observed, **kwargs):
    lifecycle = next_lifecycle(row, position(observed, **kwargs), now=observed)
    assert lifecycle is not None
    row["extra_data"] = {**row["extra_data"], "voyage_lifecycle": lifecycle}
    return lifecycle


def test_two_moored_observations_then_first_movement_ends_voyage():
    row = shipment()
    assert advance(row, T0)["state"] == "berth_candidate"
    assert advance(row, T0 + timedelta(minutes=10))["state"] == "berthed"
    assert advance(row, T0 + timedelta(minutes=20), speed=4, nav="under way")["state"] == "ended"


def test_anchor_only_and_unknown_or_wrong_port_cannot_end_coverage():
    row = shipment(port="中国主要港口")
    assert next_lifecycle(row, position(T0), now=T0) is None
    row = shipment()
    assert next_lifecycle(row, position(T0, nav="at anchor"), now=T0) is None
    assert next_lifecycle(row, position(T0, latitude=20, longitude=110), now=T0) is None


def test_stale_duplicate_and_pre_etd_positions_are_ignored():
    row = shipment()
    assert next_lifecycle(row, position(T0), now=T0 + timedelta(hours=3)) is None
    assert next_lifecycle(row, position(T0 - timedelta(days=2)), now=T0 - timedelta(days=2)) is None
    advance(row, T0)
    assert next_lifecycle(row, position(T0), now=T0) is None


class FakeGateway:
    def __init__(self, rows):
        self.rows = rows
        self.declarations = {row["declaration_id"]: {"id": row["declaration_id"], "policy_id": "p1", "status": "confirmed"} for row in rows}
        self.saved = []
        self.completed = []
        self.stopped = []

    def list_shipments(self, imo):
        return self.rows

    def list_ended_imos(self):
        return ["9127136"] if any(row.get("coverage_status") == ENDED_STATUS for row in self.rows) else []

    def list_declarations(self, ids):
        return [self.declarations[item] for item in ids]

    def list_policies(self, ids):
        return [{"id": "p1", "status": "active"}]

    def save_transition(self, row, lifecycle):
        self.saved.append((row["id"], lifecycle["state"]))
        return True

    def complete_declaration(self, declaration_id):
        self.completed.append(declaration_id)

    def stop_insurance_tracking(self, imo):
        self.stopped.append(imo)
        return True


def test_same_vessel_keeps_tracking_until_all_active_declarations_end():
    first = shipment(extra={"insurance_tracking_owned": True})
    second = shipment("s2", "d2", port="天津港")
    gateway = FakeGateway([first, second])
    service = VoyageLifecycleService(gateway)
    for observed, speed, nav in ((T0, 0, "moored"), (T0 + timedelta(minutes=10), 0, "moored"), (T0 + timedelta(minutes=20), 4, "under way")):
        service.process_position("9127136", position(observed, speed=speed, nav=nav), now=observed)
    assert first["coverage_status"] == ENDED_STATUS
    assert second["coverage_status"] is None
    assert gateway.completed == ["d1"]
    assert gateway.stopped == []


def test_last_owned_shipment_ends_and_stops_tracking():
    gateway = FakeGateway([shipment(extra={"insurance_tracking_owned": True})])
    service = VoyageLifecycleService(gateway)
    for observed, speed, nav in ((T0, 0, "moored"), (T0 + timedelta(minutes=10), 0, "moored"), (T0 + timedelta(minutes=20), 4, "under way")):
        service.process_position("9127136", position(observed, speed=speed, nav=nav), now=observed)
    assert gateway.completed == ["d1"]
    assert gateway.stopped == ["9127136"]
    assert service.process_position("9127136", position(T0 + timedelta(minutes=30), speed=5), now=T0 + timedelta(minutes=30)) == []


def test_tracking_not_stopped_when_not_owned_by_insurance():
    gateway = FakeGateway([shipment()])
    service = VoyageLifecycleService(gateway)
    for observed, speed, nav in ((T0, 0, "moored"), (T0 + timedelta(minutes=10), 0, "moored"), (T0 + timedelta(minutes=20), 4, "under way")):
        service.process_position("9127136", position(observed, speed=speed, nav=nav), now=observed)
    assert gateway.completed == ["d1"]
    assert gateway.stopped == []


def test_reconciliation_retries_completion_and_tracking_release():
    row = shipment(extra={"insurance_tracking_owned": True})
    row["coverage_status"] = ENDED_STATUS
    row["extra_data"]["voyage_lifecycle"] = {"state": "ended", "ended_at": T0.isoformat()}
    gateway = FakeGateway([row])
    VoyageLifecycleService(gateway).reconcile_finished()
    assert gateway.completed == ["d1"]
    assert gateway.stopped == ["9127136"]

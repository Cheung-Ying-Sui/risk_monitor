from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import pytest

from fastapi.testclient import TestClient

from api.main import app
from api.routes.port_weather import get_arrivals_repository
from risk_monitor.port_arrivals import get_port_arrivals, match_destination_ports, PORT_ALIASES


SHANGHAI = ZoneInfo("Asia/Shanghai")


class FakeRepository:
    def __init__(self, shipments=None, declarations=None, policies=None):
        self.shipments = shipments or []
        self.declarations = declarations or []
        self.policies = policies or []
        self.window = None

    def list_eta_shipments(self, start, end):
        self.window = (start, end)
        return self.shipments

    def get_declarations(self, ids):
        return [row for row in self.declarations if row["id"] in ids]

    def get_policies(self, ids):
        return [row for row in self.policies if row["id"] in ids]


def shipment(sid, name, imo, port, eta, declaration_id="dec-1", updated_at=None):
    return {"id": sid, "declaration_id": declaration_id, "vessel_name": name,
            "imo_number": imo, "discharge_port": port, "eta": eta.isoformat(),
            "updated_at": (updated_at or eta).isoformat()}


def test_arrivals_use_shanghai_today_plus_five_days_and_exact_port_match():
    now = datetime(2026, 10, 11, 10, tzinfo=SHANGHAI).astimezone(timezone.utc)
    repo = FakeRepository(
        shipments=[
            shipment("past", "PAST", "1111111", "zhanjiang", now - timedelta(minutes=1)),
            shipment("valid", "NIGHTWING", "9281712", " zhanjiang ", now + timedelta(days=1)),
            shipment("generic", "GENERIC", "2222222", "China main port(s)", now + timedelta(days=1)),
            shipment("other", "OTHER", "3333333", "QINGDAO", now + timedelta(days=1)),
            shipment("last", "LAST", "4444444", "湛江港", datetime(2026, 10, 16, 23, 59, tzinfo=SHANGHAI)),
            shipment("boundary", "TOO LATE", "5555555", "湛江港", datetime(2026, 10, 17, tzinfo=SHANGHAI)),
        ],
        declarations=[{"id": "dec-1", "status": "confirmed", "policy_id": "policy-1"}],
        policies=[{"id": "policy-1", "status": "active"}],
    )

    result = get_port_arrivals("CN_ZHANJIANG", repository=repo, now=now)

    assert [row["vessel_name"] for row in result["arrivals"]] == ["NIGHTWING", "LAST"]
    assert result["arrivals"][0]["eta_source"] == "insurance_declaration"
    assert repo.window[0] == now
    assert repo.window[1] == datetime(2026, 10, 17, tzinfo=SHANGHAI).astimezone(timezone.utc)


def test_arrivals_exclude_unconfirmed_cancelled_policy_and_dedupe_vessel():
    now = datetime(2026, 10, 11, tzinfo=timezone.utc)
    repo = FakeRepository(
        shipments=[
            shipment("old", "A", "1111111", "青岛港", now + timedelta(days=2), updated_at=now),
            shipment("new", "A", "1111111", "CNQDG", now + timedelta(days=3), updated_at=now + timedelta(hours=1)),
            shipment("draft", "DRAFT", "2222222", "青岛港", now + timedelta(days=1), "dec-2"),
            shipment("cancelled", "CANCELLED", "3333333", "青岛港", now + timedelta(days=1), "dec-3"),
        ],
        declarations=[
            {"id": "dec-1", "status": "covered", "policy_id": "policy-1"},
            {"id": "dec-2", "status": "draft", "policy_id": "policy-1"},
            {"id": "dec-3", "status": "confirmed", "policy_id": "policy-2"},
        ],
        policies=[{"id": "policy-1", "status": "active"}, {"id": "policy-2", "status": "cancelled"}],
    )

    result = get_port_arrivals("CN_QINGDAO", repository=repo, now=now)

    assert len(result["arrivals"]) == 1
    assert result["arrivals"][0]["eta"] == (now + timedelta(days=3)).isoformat()


def test_arrivals_api_returns_minimal_fields_and_rejects_unknown_port():
    now = datetime.now(timezone.utc)
    repo = FakeRepository(
        shipments=[shipment("one", "SHIP ONE", "1234567", "Zhanjiang", now + timedelta(days=1))],
        declarations=[{"id": "dec-1", "status": "confirmed", "policy_id": "policy-1"}],
        policies=[{"id": "policy-1", "status": "active"}],
    )
    app.dependency_overrides[get_arrivals_repository] = lambda: repo
    try:
        client = TestClient(app)
        response = client.get("/api/v1/port-weather/ports/CN_ZHANJIANG/arrivals")
        assert response.status_code == 200
        assert response.json()["arrivals"][0]["vessel_name"] == "SHIP ONE"
        item = response.json()['arrivals'][0]
        assert item['eta_source'] == 'insurance_declaration'
        assert item['eta_scope'] == 'declaration_voyage'
        assert item['declaration_id'] == 'dec-1'
        assert item['discharge_port'] == 'Zhanjiang'
        assert client.get("/api/v1/port-weather/ports/CN_OTHER/arrivals").status_code == 404
    finally:
        app.dependency_overrides.pop(get_arrivals_repository, None)


@pytest.mark.parametrize('code,alias', [(code, alias) for code, aliases in PORT_ALIASES.items() for alias in aliases | {code}])
def test_all_pilot_aliases(code, alias):
    assert match_destination_ports(f'  {alias.lower()}  ') == {code}


@pytest.mark.parametrize('value', ['天津、青岛', '天津，青岛', '天津, 青岛', ' 天津； 青岛;天津 ', 'TIANJIN | cnqdg', '天津｜青岛', 'Ｔｉａｎｊｉｎ，Qingdao'])
def test_multiple_exact_fragments(value):
    assert match_destination_ports(value) == {'CN_TIANJIN', 'CN_QINGDAO'}


@pytest.mark.parametrize('value', [None, '', ' , ; 、 ', '上海港', '青岛附近', '天津到青岛', '天津 青岛', 'China main port(s)', '预计抵达青岛', 'Qingdao area'])
def test_unrelated_or_ambiguous_text_is_not_guessed(value):
    assert not match_destination_ports(value)


def test_multi_destination_preserves_source_and_ignores_via_port():
    now = datetime(2026, 10, 13, 23, 30, tzinfo=SHANGHAI)
    raw = '天津、 青岛；天津'
    row = shipment('s1', 'TEST VESSEL', '1234567', raw, now + timedelta(hours=1))
    row['via_port'] = '连云港'
    repo = FakeRepository([row], [{'id': 'dec-1', 'status': 'confirmed', 'policy_id': 'p'}], [{'id': 'p', 'status': 'active'}])
    for code in ['CN_TIANJIN', 'CN_QINGDAO']:
        result = get_port_arrivals(code, repository=repo, now=now)
        assert result['port_code'] == code
        assert len(result['arrivals']) == 1
        item = result['arrivals'][0]
        assert item['discharge_port'] == raw
        assert item['declaration_id'] == 'dec-1' and item['shipment_id'] == 's1'
        assert item['eta_scope'] == 'declaration_voyage'
        assert item['eta'] == (now + timedelta(hours=1)).astimezone(timezone.utc).isoformat()
    assert not get_port_arrivals('CN_LIANYUNGANG', repository=repo, now=now)['arrivals']
    assert row['discharge_port'] == raw


@pytest.mark.parametrize('status', ['draft', 'pending_review', 'cancelled', 'completed'])
def test_ineligible_declarations_are_excluded_for_all_matched_ports(status):
    now = datetime(2026, 10, 13, tzinfo=SHANGHAI)
    repo = FakeRepository([shipment('s', 'TEST', '1234567', '天津、青岛', now)],
        [{'id': 'dec-1', 'status': status, 'policy_id': 'p'}], [{'id': 'p', 'status': 'active'}])
    for code in ['CN_TIANJIN', 'CN_QINGDAO']:
        assert not get_port_arrivals(code, repository=repo, now=now)['arrivals']

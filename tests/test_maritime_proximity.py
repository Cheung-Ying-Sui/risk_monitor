from datetime import datetime, timedelta, timezone
from math import degrees
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from risk_monitor.maritime_proximity import (EARTH_RADIUS_NM, calculate_counts, coordinates,
    distance_nm, matches_insured_vessel, query_counts)
from 情报收集模块.ukmto.api import router, get_incident_repository, get_proximity_repository
from 情报收集模块.ukmto.query_repository import IncidentFilters

NOW = datetime(2026, 10, 13, tzinfo=timezone.utc)


def vessel(id='new-dynamic-id', lat=0, lon=0, age=0):
    return dict(vessel_id=id, imo='1234567', mmsi='123456789', name='Actual vessel',
                latest_position=dict(latitude=lat, longitude=lon, observed_at=(NOW-timedelta(hours=age)).isoformat()))


def event(id='source-id', lat=0, lon=0):
    return dict(external_id=id, latitude=lat, longitude=lon)


def test_spherical_distance_equator_dateline_and_hemispheres():
    assert distance_nm((0, 0), (0, 1)) == pytest.approx(60.04054, abs=.0001)
    assert distance_nm((0, 179), (0, -179)) == pytest.approx(120.08108, abs=.0001)
    assert distance_nm((-10, 20), (10, 20)) == pytest.approx(1200.8108, abs=.001)
    assert distance_nm((-45, -90), (-45, -90)) == 0


def test_500_nm_boundary_dedup_and_independent_vessels():
    boundary = degrees(500/EARTH_RADIUS_NM)
    events = [event(), event(), event('edge', lon=boundary), event('outside', lon=boundary+.00001)]
    rows = calculate_counts([vessel(), vessel('distant', lat=-60, lon=-120)], events, NOW)
    assert rows[0]['event_count'] == 2
    assert rows[0]['event_ids'] == ['source-id', 'edge']
    assert rows[1]['event_count'] == 0


@pytest.mark.parametrize('lat,lon', [(None, 2), (91, 0), (0, 181), (float('nan'), 0), (0, float('inf')), ('x', 2), (True, 0)])
def test_invalid_coordinates_never_count(lat, lon):
    assert coordinates({'latitude': lat, 'longitude': lon}) is None
    assert calculate_counts([vessel()], [event(lat=lat, lon=lon)], NOW)[0]['event_count'] == 0
    row = calculate_counts([vessel(lat=lat, lon=lon)], [event()], NOW)[0]
    assert row['event_count'] is None and row['calculation_status'] == 'position_unavailable'


@pytest.mark.parametrize('age,status', [(24, 'ok'), (24.001, 'position_stale'), (-1, 'position_stale')])
def test_position_age(age, status):
    row = calculate_counts([vessel(age=age)], [event()], NOW)[0]
    assert row['calculation_status'] == status
    assert (row['event_count'] is None) == (status != 'ok')


@pytest.mark.parametrize('position', [None, {}, {'latitude': 1, 'longitude': 2, 'observed_at': 'bad'},
    {'latitude': 1, 'longitude': 2, 'observed_at': '2026-10-13T00:00:00'}])
def test_missing_or_ambiguous_position_is_not_zero(position):
    assert calculate_counts([{**vessel(), 'latest_position': position}], [event()], NOW)[0]['event_count'] is None


def test_identifier_precedence_matches_frontend():
    insured = dict(imo_number='1234567', confirmed_mmsi='123456789', vessel_name='Actual')
    assert matches_insured_vessel(dict(imo='1234567', ship_name='Renamed'), insured)
    assert not matches_insured_vessel(dict(imo='7654321', mmsi='123456789'), insured)
    assert not matches_insured_vessel(dict(ship_name='Actual'), insured)
    assert matches_insured_vessel(dict(mmsi='123456789'), insured)
    assert matches_insured_vessel(dict(ship_name=' ACTUAL '), dict(vessel_name='Actual'))


def test_pagination_reuses_all_filters_not_requested_page():
    repository, incidents = Mock(), Mock()
    repository.insured_positions.return_value = [vessel()]
    incidents.list.side_effect = [([event()], 2), ([event('second')], 2)]
    filters = IncidentFilters(NOW-timedelta(days=7), NOW, 'attack', 'region', 'active', 1, 80)
    result = query_counts(repository, incidents, filters, NOW)
    assert result['items'][0]['event_count'] == 2
    for call in incidents.list.call_args_list:
        f = call.args[0]
        assert (f.from_time, f.to_time, f.incident_type, f.region, f.status) == (filters.from_time, NOW, 'attack', 'region', 'active')
        assert call.kwargs == {'coordinates_only': True}
    assert [c.args[0].offset for c in incidents.list.call_args_list] == [0, 1]


def test_partial_or_oversized_query_fails_instead_of_zero():
    repository, incidents = Mock(), Mock()
    repository.insured_positions.return_value = [vessel()]
    for response in [([], 2), ([], 50001)]:
        incidents.list.return_value = response
        with pytest.raises(RuntimeError):
            query_counts(repository, incidents, IncidentFilters(), NOW)


def test_api_filters_dynamic_identity_and_errors():
    app = FastAPI()
    app.include_router(router)
    repository, incidents = Mock(), Mock()
    current = datetime.now(timezone.utc).isoformat()
    repository.insured_positions.return_value = [{**vessel('any-new-confirmed-vessel'), 'latest_position': dict(latitude=0, longitude=0, observed_at=current)}]
    incidents.list.return_value = ([event()], 1)
    app.dependency_overrides[get_proximity_repository] = lambda: repository
    app.dependency_overrides[get_incident_repository] = lambda: incidents
    with TestClient(app) as client:
        path = '/api/v1/ukmto/vessel-risk-counts'
        response = client.get(path, params={'incident_type': 'attack', 'from': '2026-10-01', 'to': '2026-10-31'})
        assert response.status_code == 200
        assert response.json()['items'][0]['vessel_id'] == 'any-new-confirmed-vessel'
        assert response.json()['items'][0]['event_count'] == 1
        assert response.json()['time_basis'] == 'published_at_utc'
        assert client.get(path+'?incident_type=invalid').status_code == 422
        assert client.get(path+'?from=2026-10-31&to=2026-10-01').status_code == 422
        incidents.list.side_effect = RuntimeError('private credentials')
        failed = client.get(path)
        assert failed.status_code == 503 and 'private credentials' not in failed.text


def test_repository_uses_confirmed_dynamic_projection_and_batch_reads(monkeypatch):
    from types import SimpleNamespace
    from risk_monitor.maritime_proximity import ProximityRepository
    from risk_monitor.insurance_repository import InsuranceRepository
    from risk_monitor import supabase_client
    declarations = []
    monkeypatch.setattr(InsuranceRepository, 'list_policies', lambda *_args, **_kwargs: [{'id': 'p', 'status': 'active'}])
    monkeypatch.setattr(InsuranceRepository, 'list_declarations', lambda *_args, **_kwargs: declarations)
    tables = {
        'tracked_vessels': [{'vessel_id': 'new-id', 'is_active': True}],
        'vessels': [{'id': 'new-id', 'imo': '1234567', 'mmsi': '123456789', 'ship_name': 'New ship'}],
        'latest_vessel_positions': [{**vessel()['latest_position'], 'vessel_id': 'new-id'}],
    }
    calls = []
    class Query:
        def schema(self, _): return self
        def table(self, name):
            self.name, self.rows = name, list(tables[name])
            return self
        def select(self, _): return self
        def eq(self, key, value):
            self.rows = [r for r in self.rows if r.get(key) == value]
            return self
        def in_(self, key, values):
            self.rows = [r for r in self.rows if r.get(key) in values]
            return self
        def order(self, _): return self
        def range(self, start, end):
            self.rows = self.rows[start:end+1]
            return self
        def execute(self):
            calls.append(self.name)
            return SimpleNamespace(data=self.rows)
    monkeypatch.setattr(supabase_client, 'supabase', Query())
    repo = ProximityRepository()
    assert repo.insured_positions() == []
    declaration = dict(id='arbitrary-new-declaration', declaration_number='ANY-NEW', policy_id='p', status='pending_review',
                       shipments=[dict(vessel_name='New ship', imo_number='1234567')])
    declarations.append(declaration)
    assert repo.insured_positions() == []
    declaration['status'] = 'confirmed'
    assert repo.insured_positions()[0]['vessel_id'] == 'new-id'
    assert calls == ['tracked_vessels', 'vessels', 'latest_vessel_positions']
    declaration['shipments'][0]['coverage_status'] = 'ended_by_mvp_departure'
    assert repo.insured_positions() == []

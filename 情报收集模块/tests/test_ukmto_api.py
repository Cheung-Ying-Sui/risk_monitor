from datetime import timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from 情报收集模块.ukmto.api import router, get_incident_repository, _database_client
from 情报收集模块.ukmto.query_repository import IncidentFilters, IncidentQueryRepository, PUBLIC_COLUMNS

BASE = '/api/v1/ukmto'
app = FastAPI()
app.include_router(router)
ROW = dict(external_id='UKMTO-2026-141', incident_type='attack', title='Report',
           source_url='https://www.ukmto.org/recent-incidents#test', latitude=12.6,
           longitude=48.2, location_precision='approximate', location_text='85NM south of Balhaf',
           published_at='2026-09-22T10:00:00Z', raw_payload={'private': 'hidden'}, content_hash='hidden')


@pytest.fixture
def repository():
    repo = Mock()
    repo.list.return_value = ([ROW], 1)
    repo.get.return_value = ROW
    app.dependency_overrides[get_incident_repository] = lambda: repo
    yield repo
    app.dependency_overrides.pop(get_incident_repository, None)


@pytest.fixture
def client():
    with TestClient(app) as session:
        yield session


def test_list_public_fields_and_nulls(client, repository):
    repository.list.return_value = ([{**ROW, 'latitude': None, 'longitude': None}], 1)
    response = client.get(BASE + '/incidents')
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 1 and data['next_offset'] is None
    assert data['items'][0]['latitude'] is None
    assert data['items'][0]['incident_time'] is None
    assert data['items'][0]['location_text'] == ROW['location_text']
    assert 'raw_payload' not in data['items'][0]
    assert 'content_hash' not in data['items'][0]


def test_filter_and_pagination(client, repository):
    repository.list.return_value = ([ROW], 12)
    response = client.get(BASE + '/incidents', params={'from': '2026-09-01', 'to': '2026-09-23T08:00:00+08:00',
                          'incident_type': 'attack', 'region': 'IO', 'status': 'active', 'limit': 1, 'offset': 2})
    assert response.status_code == 200
    assert response.json()['next_offset'] == 3
    assert response.json()['has_more'] is True
    filters = repository.list.call_args.args[0]
    assert filters.from_time.tzinfo == timezone.utc
    assert filters.to_time.hour == 0
    assert (filters.incident_type, filters.region, filters.status, filters.limit, filters.offset) == ('attack', 'IO', 'active', 1, 2)


@pytest.mark.parametrize('params', [{'limit': 0}, {'limit': 1001}, {'offset': -1}, {'limit': 'bad'},
    {'incident_type': 'invalid'}, {'from': 'bad'}, {'from': '2026-09-23', 'to': '2026-09-01'}, {'region': ''}])
def test_invalid_queries(client, repository, params):
    assert client.get(BASE + '/incidents', params=params).status_code == 422
    repository.list.assert_not_called()


def test_geojson_order_precision_and_pagination(client, repository):
    response = client.get(BASE + '/incidents.geojson')
    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/geo+json'
    body = response.json()
    assert body['type'] == 'FeatureCollection'
    feature = body['features'][0]
    assert feature['geometry'] == {'type': 'Point', 'coordinates': [48.2, 12.6]}
    assert feature['properties']['location_precision'] == 'approximate'
    assert body['pagination']['total'] == 1
    assert repository.list.call_args.kwargs['coordinates_only'] is True
    repository.get.assert_not_called()


def test_geojson_does_not_invent_coordinates(client, repository):
    repository.list.return_value = ([{**ROW, 'latitude': None, 'longitude': None}, {**ROW, 'latitude': 0, 'longitude': 0}], 2)
    features = client.get(BASE + '/incidents.geojson').json()['features']
    assert len(features) == 1 and features[0]['geometry']['coordinates'] == [0, 0]


def test_empty_and_out_of_range_page(client, repository):
    repository.list.return_value = ([], 12)
    body = client.get(BASE + '/incidents?offset=100').json()
    assert body['items'] == [] and body['total'] == 12
    assert body['has_more'] is False and body['next_offset'] is None
    repository.list.return_value = ([], 0)
    assert client.get(BASE + '/incidents.geojson').json()['features'] == []


def test_detail_and_missing(client, repository):
    response = client.get(BASE + '/incidents/UKMTO-2026-141')
    assert response.status_code == 200 and 'raw_payload' not in response.json()
    repository.get.assert_called_with('UKMTO-2026-141')
    repository.get.return_value = None
    assert client.get(BASE + '/incidents/missing').status_code == 404


@pytest.mark.parametrize('path', ['/incidents', '/incidents.geojson', '/incidents/id'])
def test_database_failures_hide_details(client, repository, path):
    repository.list.side_effect = RuntimeError('Authorization: secret-data')
    repository.get.side_effect = RuntimeError('Authorization: secret-data')
    response = client.get(BASE + path)
    assert response.status_code == 503
    assert 'secret-data' not in response.text


def test_missing_config_does_not_break_app(client, monkeypatch):
    _database_client.cache_clear()
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED', '1')
    for key in ['SUPABASE_URL', 'SUPABASE_SERVICE_KEY', 'SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_SECRET_KEY']:
        monkeypatch.delenv(key, raising=False)
    assert client.get('/openapi.json').status_code == 200
    assert client.get(BASE + '/incidents').status_code == 503
    _database_client.cache_clear()


def test_repository_projects_filters_orders_before_pagination():
    db = Mock()
    query = Mock()
    db.table.return_value = query
    for method in ['select', 'eq', 'gte', 'lte', 'order', 'range', 'limit']:
        getattr(query, method).return_value = query
    query.execute.return_value = SimpleNamespace(data=[ROW], count=61)
    repo = IncidentQueryRepository(db)
    filters = IncidentFilters(incident_type='attack', region='IO', status='active', limit=20, offset=40)
    assert repo.list(filters, coordinates_only=True) == ([ROW], 61)
    assert 'raw_payload' not in PUBLIC_COLUMNS and '*' not in PUBLIC_COLUMNS
    query.select.assert_called_once_with(PUBLIC_COLUMNS, count='exact')
    names = [call[0] for call in query.mock_calls]
    assert names.index('gte') < names.index('range')
    query.range.assert_called_with(40, 59)
    assert ('latitude', -90) in [call.args for call in query.gte.call_args_list]
    assert ('longitude', 180) in [call.args for call in query.lte.call_args_list]
    assert ('source', 'UKMTO') in [call.args for call in query.eq.call_args_list]
    assert ('region', 'IO') in [call.args for call in query.eq.call_args_list]
    assert len(query.order.call_args_list) == 2


def test_openapi_contains_new_routes(client):
    paths = client.get('/openapi.json').json()['paths']
    for suffix in ['/incidents', '/incidents.geojson', '/incidents/{external_id}']:
        assert BASE + suffix in paths

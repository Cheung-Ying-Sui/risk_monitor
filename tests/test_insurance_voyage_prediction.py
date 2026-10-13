from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from api.main import app
from api.routes.navigation import get_insurance_prediction_service
from risk_monitor.insurance_repository import InsuranceRepository
from risk_monitor.navigation.insurance_prediction_service import (
    InsuranceVoyagePredictionService, destination_decision, compatible_route,
    voyage_context, check_progress_evidence,
)
from risk_monitor.navigation.destination_normalizer import resolve_destination
from risk_monitor.navigation.route_progress import calculate_route_progress, RouteProjectionAmbiguous

NOW = datetime(2026, 10, 13, tzinfo=timezone.utc)


def shipment(id='s-new', declaration='d-new', destination='SGSIN'):
    return dict(id=id, declaration_id=declaration, declaration_number=f'REF-{declaration}',
                declaration_status='confirmed', discharge_port=destination, loading_port='Shanghai',
                imo_number='1234567', vessel_name='Any new ship', extra_data={}, etd=None)


class Repository:
    def __init__(self, rows=None):
        self.rows = rows if rows is not None else [shipment()]
        self.vessel = dict(id='dynamic-vessel', imo='1234567', mmsi='123456789')
        self.position = dict(latitude=0, longitude=0, sog=12, cog=90, observed_at=NOW.isoformat(),
                             destination='SGSIN', vessel_id='dynamic-vessel', mmsi='123456789', position_id=1)
        self.route, self.history_routes, self.generations = None, [], 0
    def list_shipments(self):
        return [r for r in self.rows if r['declaration_status'] in {'confirmed','covered'} and r.get('coverage_status') != 'ended_by_mvp_departure']
    def find_tracked_vessel(self, _): return self.vessel
    def get_latest_position(self, _): return self.position
    def get_active_route(self, _): return self.route
    def reconcile(self, *_): pass
    def history(self, _): return []
    def get_speed_history(self, *_, **__): return [{'sog': 12}]
    def ensure_route(self, vessel, position, destination, context):
        if not compatible_route(self.route, vessel, context):
            if self.route: self.history_routes.append(deepcopy(self.route))
            self.generations += 1
            self.route = dict(route_prediction_id=f'route-{self.generations}', route_version=self.generations,
                status='active', vessel_id=vessel['id'], mmsi=vessel['mmsi'],
                destination_unlocode=destination['unlocode'], destination_normalized=destination['normalized_destination'],
                route_geojson={'type': 'LineString', 'coordinates': [[position['longitude'],position['latitude']], [10,0]],
                               'insurance_voyage': context, 'insurance_origin_observed_at': position['observed_at']})
        return self.route


@pytest.mark.parametrize('decl,ais,source,status', [
    ('青岛港','CNQDG','declaration','eligible'), ('连云港','LIANYUNGANG','declaration','eligible'),
    ('SGSIN','CNSHA','declaration','destination_mismatch'), ('SGSIN',None,'declaration','eligible'),
    ('SGSIN','FOR ORDERS','declaration','eligible'), (None,'SGSIN','ais_fallback','eligible'),
    ('unresolved','SGSIN','ais_fallback','eligible'), (None,None,None,'destination_unresolved'),
    ('天津、青岛','CNQDG',None,'destination_unresolved'),
])
def test_destination_policy(decl, ais, source, status):
    d,a,s,result,_ = destination_decision(decl,ais)
    assert (s,result) == (source,status)
    assert d['raw_destination'] == (decl or '')
    assert a['raw_destination'] == (ais or '')


def test_missing_stale_and_invalid_ais_never_expose_old_progress():
    repo = Repository()
    service = InsuranceVoyagePredictionService(repo)
    assert service.list_predictions(refresh=True,now=NOW)[0]['status']=='estimated'
    for position,status in [(None,'position_unavailable'), ({**repo.position,'latitude':float('nan')},'position_unavailable'),
                            ({**repo.position,'observed_at':(NOW-timedelta(hours=25)).isoformat()},'ais_stale')]:
        repo.position = position
        row = service.list_predictions(now=NOW)[0]
        assert row['status']==status and row['prediction'] is None and row['progress'] is None and row['eta'] is None


def test_complete_then_new_voyage_retains_history_but_regenerates_from_current_ais():
    repo = Repository()
    service = InsuranceVoyagePredictionService(repo)
    original = service.list_predictions(refresh=True,now=NOW)[0]
    assert original['shipment_id']=='s-new' and original['progress']==0
    repo.rows[0]['coverage_status']='ended_by_mvp_departure'
    repo.rows[0]['declaration_status']='completed'
    assert service.list_predictions(refresh=True,now=NOW)==[]
    assert repo.route['route_prediction_id']==original['route_prediction_id']
    repo.rows.append(shipment('later-shipment','later-declaration','CNSHA'))
    repo.position.update(longitude=3, destination='CNSHA', position_id=2)
    later = service.list_predictions(refresh=True,now=NOW)[0]
    assert later['shipment_id']=='later-shipment' and later['declaration_id']=='later-declaration'
    assert later['route_version']==2 and later['progress']==0
    assert later['prediction']['route']['geojson']['coordinates'][0]==[3,0]
    assert repo.history_routes[0]['route_prediction_id']==original['route_prediction_id']


def test_same_vessel_same_destination_shares_route_keeps_each_association():
    repo=Repository([shipment('a','da'),shipment('b','db')])
    rows=InsuranceVoyagePredictionService(repo).list_predictions(refresh=True,now=NOW)
    assert len(rows)==2 and repo.generations==1
    assert {r['shipment_id'] for r in rows}=={'a','b'}
    assert {r['route_prediction_id'] for r in rows}=={'route-1'}


def test_conflicting_active_shipments_block_route_creation():
    repo=Repository([shipment('a','da'),shipment('b','db','CNSHA')])
    rows=InsuranceVoyagePredictionService(repo).list_predictions(refresh=True,now=NOW)
    assert all(r['status']=='ambiguous_active_shipments' and r['prediction'] is None for r in rows)
    assert repo.generations==0


def test_destination_mismatch_and_changed_identity_never_reuse_old_route():
    repo=Repository()
    service=InsuranceVoyagePredictionService(repo)
    service.list_predictions(refresh=True,now=NOW)
    repo.position['destination']='CNSHA'
    row=service.list_predictions(refresh=True,now=NOW)[0]
    assert row['status']=='destination_mismatch' and row['progress'] is None and repo.generations==1
    repo.position['destination']='SGSIN'
    repo.rows[0]['id']='another-shipment'
    row=service.list_predictions(now=NOW)[0]
    assert row['status']=='route_pending' and row['prediction'] is None
    assert service.list_predictions(refresh=True,now=NOW)[0]['route_version']==2


def test_ais_fallback_is_explicit_and_lower_confidence():
    normal=InsuranceVoyagePredictionService(Repository()).list_predictions(refresh=True,now=NOW)[0]
    fallback=InsuranceVoyagePredictionService(Repository([shipment(destination=None)])).list_predictions(refresh=True,now=NOW)[0]
    assert fallback['destination_source']=='ais_fallback'
    assert fallback['confidence'] < normal['confidence']
    assert 'ais_fallback_needs_review' in fallback['warnings']


def test_eligibility_projection_excludes_inactive_policies_and_shipments():
    repo=InsuranceRepository()
    repo.list_policies=lambda **_: [{'id':'valid','status':'active'},{'id':'void','status':'cancelled'}]
    rows=[dict(id=f'd-{i}',status=status,policy_id=policy,declaration_number=f'REF-{i}',shipments=[dict(id=f's-{i}',coverage_status=coverage,extra_data={})])
          for i,(status,policy,coverage) in enumerate([
              ('confirmed','valid',None),('covered','valid',None),('completed','valid',None),
              ('pending_review','valid',None),('cancelled','valid',None),('demo','valid',None),
              ('confirmed','void',None),('confirmed','missing',None),('confirmed','valid','ended_by_mvp_departure')])]
    repo.list_declarations=lambda status,**_: [r for r in rows if r['status']==status]
    assert {r['id'] for r in repo.list_prediction_shipments()}=={'s-0','s-1'}


@pytest.mark.parametrize('line,point', [
    ([[0,0],[5,0],[0,0]],{'longitude':2,'latitude':0}),
    ([[-1,-1],[1,1],[-1,1],[1,-1]],{'longitude':0,'latitude':0}),
])
def test_return_leg_and_self_intersection_are_not_resolved_by_nearest_point(line, point):
    with pytest.raises(RouteProjectionAmbiguous):
        calculate_route_progress(point,{'type':'LineString','coordinates':line},reject_ambiguous=True)


def test_progress_jump_and_backward_evidence_fail_instead_of_forced_monotonicity():
    route={'route_geojson':{'type':'LineString','coordinates':[[0,0],[10,0]],'insurance_origin_observed_at':(NOW-timedelta(hours=10)).isoformat()}}
    position={'longitude':5,'latitude':0,'observed_at':NOW.isoformat()}
    for longitude in [0,8]:
        previous={'longitude':longitude,'latitude':0,'observed_at':(NOW-timedelta(minutes=1)).isoformat()}
        with pytest.raises(ValueError,match='route_progress_jump'):
            check_progress_evidence(None,route,position,[previous])


def test_cannot_reuse_route_with_other_vessel_or_context():
    repo=Repository()
    destination=resolve_destination('SGSIN')
    ctx=voyage_context(repo.rows,repo.vessel,destination)
    route=repo.ensure_route(repo.vessel,repo.position,destination,ctx)
    assert compatible_route(route,repo.vessel,ctx)
    assert not compatible_route({**route,'vessel_id':'other'},repo.vessel,ctx)
    assert not compatible_route({**route,'status':'superseded'},repo.vessel,ctx)


def test_api_uses_service_projection_and_schedules_pending_generation():
    service=Mock()
    service.list_predictions.return_value=[{'shipment_id':'dynamic','status':'route_pending'}]
    app.dependency_overrides[get_insurance_prediction_service]=lambda:service
    try:
        client=TestClient(app)
        response=client.get('/api/v1/insurance/voyage-predictions')
        assert response.status_code==200 and response.json()['items'][0]['shipment_id']=='dynamic'
        assert service.list_predictions.call_count==2
        service.list_predictions.assert_called_with(refresh=True)
        service.list_predictions.side_effect=RuntimeError('secret')
        response=client.get('/api/v1/insurance/voyage-predictions')
        assert response.status_code==503 and 'secret' not in response.text
    finally:
        app.dependency_overrides.pop(get_insurance_prediction_service,None)

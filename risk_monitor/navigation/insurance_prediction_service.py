"""Insurance eligibility/orchestration around the existing rolling route engine.

Each output is a shipment, not a permanently vessel-bound voyage. Geometry and
versions still live in navigation.route_predictions; its GeoJSON foreign member
contains the immutable insurance association, checked by the activation RPC.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import re

from risk_monitor.insurance_repository import InsuranceRepository
from risk_monitor.insurance_voyage_lifecycle import ENDED_STATUS, VoyageLifecycleService, _time
from risk_monitor.maritime_proximity import coordinates
from risk_monitor.navigation.destination_normalizer import resolve_destination
from risk_monitor.navigation.prediction_service import NavigationPredictionRepository, VesselNavigationPredictionService
from risk_monitor.navigation.route_progress import calculate_route_progress
from risk_monitor.rolling_route_repository import get_rolling_route_prediction


def destination_decision(declared, ais):
    declaration = resolve_destination(declared, use_cache=False)
    observed = resolve_destination(ais, use_cache=False)
    if len([s for s in re.split(r'[、，,；;|｜]', str(declared or '')) if s.strip()]) > 1:
        return declaration, observed, None, 'destination_unresolved', ['multiple_declared_destinations_need_review']
    if declaration['resolution_status'] == 'resolved':
        if observed['resolution_status'] == 'resolved' and declaration['unlocode'] != observed['unlocode']:
            return declaration, observed, 'declaration', 'destination_mismatch', ['declaration_ais_destination_mismatch']
        warnings = [] if observed['resolution_status'] == 'resolved' else ['ais_destination_unverified']
        return declaration, observed, 'declaration', 'eligible', warnings
    if observed['resolution_status'] == 'resolved':
        return declaration, observed, 'ais_fallback', 'eligible', ['ais_fallback_needs_review']
    return declaration, observed, None, 'destination_unresolved', ['destination_unresolved']


def voyage_context(rows, vessel, destination):
    shipments = sorted([{'shipment_id': str(r['id']), 'declaration_id': str(r['declaration_id']),
                         'discharge_port': r.get('discharge_port'), 'etd': r.get('etd')} for r in rows],
                       key=lambda r: r['shipment_id'])
    result = {'vessel_id': str(vessel['id']), 'mmsi': str(vessel['mmsi']),
              'destination_unlocode': destination['unlocode'], 'shipments': shipments}
    result['key'] = sha256(json.dumps(result, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    return result


def compatible_route(route, vessel, context):
    return bool(route and route.get('status') == 'active'
                and str(route.get('vessel_id')) == str(vessel['id'])
                and route.get('mmsi') == vessel.get('mmsi')
                and route.get('destination_unlocode') == context['destination_unlocode']
                and (route.get('route_geojson') or {}).get('insurance_voyage') == context)


class InsurancePredictionRepository(NavigationPredictionRepository):
    def list_shipments(self):
        return InsuranceRepository().list_prediction_shipments()

    def find_tracked_vessel(self, shipment):
        from risk_monitor.vessel_query_repository import get_vessel_by_imo, get_vessel_by_mmsi
        from risk_monitor.tracking_repository import get_tracking_status_by_vessel_id
        imo = str(shipment.get('imo_number') or '').strip()
        extra = shipment.get('extra_data') or {}
        mmsi = str(extra.get('mmsi_candidate') or '').strip() if extra.get('mmsi_confirmed') is True else ''
        vessel = get_vessel_by_imo(imo) if imo else get_vessel_by_mmsi(mmsi) if mmsi else None
        if not vessel or not vessel.get('mmsi'):
            return None
        if imo and str(vessel.get('imo') or '').strip() != imo:
            return None
        tracking = get_tracking_status_by_vessel_id(vessel['id'])
        return vessel if tracking and tracking.get('is_active') else None

    def ensure_route(self, vessel, position, destination, context):
        return get_rolling_route_prediction(vessel['mmsi'], insurance_context=context,
                    insurance_destination=destination, insurance_position=position)['active_route']

    def history(self, mmsi):
        from risk_monitor.trajectory_repository import get_vessel_track
        return get_vessel_track(mmsi, limit=10)

    def reconcile(self, vessel, position):
        if vessel.get('imo'):
            VoyageLifecycleService().process_position(str(vessel['imo']), position)


class _SnapshotRepository:
    """Pin identity/route/AIS for the existing calculator across concurrent reads."""
    def __init__(self, repository, vessel, position, route):
        self.repository, self.vessel, self.position, self.route = repository, vessel, position, route
    def get_vessel(self, _): return self.vessel
    def get_latest_position(self, _): return self.position
    def get_active_route(self, _): return self.route
    def get_speed_history(self, *args, **kwargs): return self.repository.get_speed_history(*args, **kwargs)


def check_progress_evidence(prediction, route, position, history):
    """Reject jumps; never clamp progress forward and pretend evidence exists."""
    geometry = route['route_geojson']
    origin = _time(geometry.get('insurance_origin_observed_at'))
    observed = _time(position.get('observed_at'))
    if not origin or not observed or observed < origin:
        raise ValueError('route_origin_time_invalid')
    current = calculate_route_progress(position, geometry, reject_ambiguous=True)
    # 80 knots is a conservative upper bound, not the ETA speed estimate.
    if current['distance_along_route_nm'] > (observed-origin).total_seconds()/3600*80 + 5:
        raise ValueError('route_progress_jump')
    previous = sorted([r for r in history if _time(r.get('observed_at')) and origin <= _time(r['observed_at']) < observed],
                      key=lambda r: _time(r['observed_at']), reverse=True)
    if previous:
        prior = calculate_route_progress(previous[0], geometry, reject_ambiguous=True)
        elapsed = (observed-_time(previous[0]['observed_at'])).total_seconds()/3600
        delta = current['distance_along_route_nm'] - prior['distance_along_route_nm']
        if delta < -5 or abs(delta) > elapsed*80 + 5:
            raise ValueError('route_progress_jump')


class InsuranceVoyagePredictionService:
    def __init__(self, repository=None):
        self.repository = repository or InsurancePredictionRepository()

    def list_predictions(self, *, refresh=False, vessel_id=None, now=None):
        now = now or datetime.now(timezone.utc)
        rows = self.repository.list_shipments()
        groups, unresolved, identities = defaultdict(list), [], {}
        for row in rows:
            # Defense in depth for alternate repositories and stale cached callers.
            if row.get('declaration_status') not in {'confirmed', 'covered'} or row.get('coverage_status') == ENDED_STATUS:
                continue
            extra = row.get('extra_data') or {}
            key = (row.get('imo_number'), json.dumps(extra.get('mmsi_candidate')), extra.get('mmsi_confirmed') is True)
            if key not in identities:
                identities[key] = self.repository.find_tracked_vessel(row)
            vessel = identities[key]
            if vessel_id and (not vessel or str(vessel['id']) != str(vessel_id)):
                continue
            if not vessel:
                unresolved.append(self._item(row, None, None, status='position_unavailable', warnings=['tracked_identity_unavailable']))
            else:
                groups[str(vessel['id'])].append((row, vessel))
        result = list(unresolved)
        for group in groups.values():
            vessel = group[0][1]
            position = self.repository.get_latest_position(vessel['id'])
            if refresh and position:
                self.repository.reconcile(vessel, position)
                active = {r['id'] for r in self.repository.list_shipments()}
                group = [(r,v) for r,v in group if r['id'] in active]
                if not group:
                    continue
            group_rows = [r for r,_ in group]
            decisions = [destination_decision(r.get('discharge_port'), (position or {}).get('destination')) for r in group_rows]
            targets = {d[0]['unlocode'] if d[2] == 'declaration' else d[1]['unlocode'] for d in decisions if d[2]}
            ambiguous = len(group_rows) > 1 and (len(targets) != 1 or any(d[3] == 'destination_unresolved' for d in decisions))
            observed = _time((position or {}).get('observed_at'))
            invalid_position = not coordinates(position or {})
            stale = not observed or not -timedelta(minutes=5) <= now-observed <= timedelta(hours=24)
            route = None
            context = None
            shared_error = None
            if not invalid_position and not stale and not ambiguous and all(d[3] == 'eligible' for d in decisions):
                destination = decisions[0][0] if decisions[0][2] == 'declaration' else decisions[0][1]
                context = voyage_context(group_rows, vessel, destination)
                try:
                    route = self.repository.ensure_route(vessel, position, destination, context) if refresh else self.repository.get_active_route(vessel['mmsi'])
                except Exception:
                    shared_error = 'route_generation_or_activation_failed'
            prediction = None
            if route and compatible_route(route, vessel, context):
                try:
                    prediction = VesselNavigationPredictionService(_SnapshotRepository(self.repository, vessel, position, route)).get_prediction(vessel['id'], prediction_timestamp=now, strict_projection=True)
                    check_progress_evidence(prediction, route, position, self.repository.history(vessel['mmsi']))
                except ValueError as exc:
                    shared_error = str(exc)
                    prediction = None
                except Exception:
                    shared_error = 'prediction_calculation_unavailable'
            for row, decision in zip(group_rows, decisions):
                declared, ais, source, status, warnings = decision
                warnings = list(warnings)
                if invalid_position:
                    status = 'position_unavailable'
                elif stale:
                    status = 'ais_stale'
                elif ambiguous:
                    status = 'ambiguous_active_shipments'
                elif status == 'eligible':
                    status = 'estimated' if prediction else 'needs_review' if shared_error and 'route_' in shared_error and ('jump' in shared_error or 'ambiguous' in shared_error) else 'route_pending'
                if shared_error:
                    warnings.append(shared_error)
                item = self._item(row, vessel, position, status=status, warnings=warnings)
                item.update(discharge_port_normalized=declared.get('unlocode'),
                            ais_destination_raw=(position or {}).get('destination'), ais_destination_normalized=ais.get('unlocode'),
                            destination_source=source, destination_normalized=(declared if source == 'declaration' else ais).get('unlocode'))
                if status == 'estimated' and prediction:
                    p = json.loads(json.dumps(prediction))
                    if source == 'ais_fallback':
                        p['prediction_quality']['confidence'] = round(p['prediction_quality']['confidence'] * .5, 3)
                        p['eta']['confidence'] = p['prediction_quality']['confidence']
                        p['destination']['confidence'] *= .5
                    p['prediction_quality']['warnings'] += warnings
                    item.update(prediction=p, route_prediction_id=route['route_prediction_id'], route_version=route['route_version'],
                                confidence=p['prediction_quality']['confidence'], progress=p['route']['progress'],
                                remaining_distance_nm=p['route']['remaining_distance_nm'], eta=p['eta']['estimated_arrival_at'])
                result.append(item)
        # Recheck eligibility at response time, including lifecycle changes during calculation.
        active_rows = {r['id']: r for r in self.repository.list_shipments()}
        final = []
        for item in result:
            current = active_rows.get(item['shipment_id'])
            if not current:
                continue
            changed = current.get('discharge_port') != item['discharge_port_raw'] or current.get('etd') != item['etd']
            if item['prediction']:
                expected = item['prediction']['route']['geojson']['insurance_voyage']
                peers = []
                for r in active_rows.values():
                    extra = r.get('extra_data') or {}
                    key = (r.get('imo_number'), json.dumps(extra.get('mmsi_candidate')), extra.get('mmsi_confirmed') is True)
                    if key not in identities:
                        identities[key] = self.repository.find_tracked_vessel(r)
                    v = identities[key]
                    if v and str(v['id']) == str(item['vessel_id']):
                        peers.append(r)
                actual = voyage_context(peers, {'id': item['vessel_id'], 'mmsi': item['mmsi']}, {'unlocode': item['destination_normalized']})
                changed = changed or actual != expected
            if changed:
                item.update(status='route_pending', prediction=None, progress=None, remaining_distance_nm=None,
                            eta=None, confidence=None, route_prediction_id=None, route_version=None,
                            warnings=['voyage_changed_during_prediction'])
            final.append(item)
        return final

    @staticmethod
    def _item(row, vessel, position, *, status, warnings):
        return {'declaration_id': row['declaration_id'], 'shipment_id': row['id'],
                'declaration_number': row['declaration_number'], 'vessel_id': (vessel or {}).get('id'),
                'vessel_name': row.get('vessel_name'), 'imo': row.get('imo_number'), 'mmsi': (vessel or {}).get('mmsi'),
                'loading_port_raw': row.get('loading_port'), 'loading_port_normalized': resolve_destination(row.get('loading_port')).get('unlocode'),
                'discharge_port_raw': row.get('discharge_port'), 'discharge_port_normalized': None,
                'etd': row.get('etd'), 'latest_ais_at': (position or {}).get('observed_at'),
                'status': status, 'destination_source': None, 'destination_normalized': None,
                'ais_destination_raw': (position or {}).get('destination'), 'ais_destination_normalized': None,
                'route_prediction_id': None, 'route_version': None, 'progress': None,
                'remaining_distance_nm': None, 'eta': None, 'confidence': None, 'warnings': warnings, 'prediction': None}

"""Read-only insured-vessel spatial screening, never a route/risk prediction."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from math import asin, cos, isfinite, radians, sin, sqrt
from time import monotonic

EARTH_RADIUS_NM = 6371.0088 / 1.852
RADIUS_NM = 500
MAX_AIS_AGE = timedelta(hours=24)


def coordinates(row):
    try:
        lat, lon = row.get('latitude'), row.get('longitude')
        if isinstance(lat, bool) or isinstance(lon, bool) or lat is None or lon is None:
            return None
        lat, lon = float(lat), float(lon)
        return (lat, lon) if isfinite(lat) and isfinite(lon) and abs(lat) <= 90 and abs(lon) <= 180 else None
    except (ValueError, TypeError):
        return None


def distance_nm(a, b):
    lat1, lon1, lat2, lon2 = map(radians, (*a, *b))
    h = sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2
    return 2 * EARTH_RADIUS_NM * asin(sqrt(max(0, min(1, h))))


def matches_insured_vessel(vessel, insured):
    """Same identifier precedence as frontend/lib/insured-vessels.ts."""
    imo, other = str(vessel.get('imo') or '').strip(), str(insured.get('imo_number') or '').strip()
    if imo and other:
        return imo == other
    mmsi, confirmed = str(vessel.get('mmsi') or '').strip(), str(insured.get('confirmed_mmsi') or '').strip()
    if mmsi and confirmed:
        return mmsi == confirmed
    if imo or other:
        return False
    name = str(vessel.get('ship_name') or '').strip().casefold()
    return bool(name) and name == str(insured.get('vessel_name') or '').strip().casefold()


class ProximityRepository:
    def insured_positions(self):
        from risk_monitor.insurance_repository import InsuranceRepository
        from risk_monitor.supabase_client import supabase
        insured = InsuranceRepository().list_insured_vessels()
        if not insured:
            return []
        # Paged, stable batch reads. No one-query-per-vessel loop.
        def read(query, order):
            rows = []
            for offset in range(0, 50000, 500):
                page = query().order(order).range(offset, offset+499).execute().data or []
                rows.extend(page)
                if len(page) < 500:
                    return rows
            raise RuntimeError('Batch too large; refusing partial counts')
        tracked = read(lambda: supabase.schema('tracking').table('tracked_vessels')
                       .select('vessel_id').eq('is_active', True), 'vessel_id')
        ids = sorted({r['vessel_id'] for r in tracked if r.get('vessel_id')})
        vessels, positions = [], []
        for offset in range(0, len(ids), 200):
            batch = ids[offset:offset+200]
            vessels.extend(read(lambda: supabase.schema('core').table('vessels')
                                .select('id,imo,mmsi,ship_name').in_('id', batch), 'id'))
            positions.extend(read(lambda: supabase.schema('tracking').table('latest_vessel_positions')
                                  .select('vessel_id,latitude,longitude,observed_at').in_('vessel_id', batch), 'vessel_id'))
        positions = {r['vessel_id']: r for r in positions}
        result, seen = [], set()
        for declaration in insured:
            vessel = next((v for v in vessels if matches_insured_vessel(v, declaration)), None)
            vessel_id = vessel['id'] if vessel else None
            if vessel_id and vessel_id in seen:
                continue
            seen.add(vessel_id)
            result.append(dict(vessel_id=vessel_id,
                               imo=(vessel or {}).get('imo') or declaration.get('imo_number'),
                               mmsi=(vessel or {}).get('mmsi') or declaration.get('confirmed_mmsi'),
                               name=declaration['vessel_name'],
                               latest_position=positions.get(vessel_id)))
        return result


def calculate_counts(vessels, events, now):
    unique = {}
    for event in events:
        point = coordinates(event)
        if event.get('external_id') and point:
            unique.setdefault(event['external_id'], point)
    if len(vessels) * len(unique) > 5_000_000:
        raise RuntimeError('Spatial batch too large; narrow event filters')
    result = []
    for vessel in vessels:
        row = {**vessel, 'radius_nm': RADIUS_NM, 'event_count': None, 'event_ids': [],
               'calculation_status': 'position_unavailable'}
        position = vessel.get('latest_position') or {}
        point = coordinates(position)
        if not point:
            row['latest_position'] = None
            result.append(row)
            continue
        try:
            observed = datetime.fromisoformat(str(position.get('observed_at')).replace('Z', '+00:00'))
            if observed.tzinfo is None:
                raise ValueError('Ambiguous timestamp')
            if now - observed > MAX_AIS_AGE or observed - now > timedelta(minutes=5):
                row['calculation_status'] = 'position_stale'
            else:
                hits = [eid for eid, location in unique.items() if distance_nm(point, location) <= RADIUS_NM + 1e-9]
                row.update(calculation_status='ok', event_count=len(hits), event_ids=hits)
        except (ValueError, TypeError):
            row['calculation_status'] = 'position_stale'
        result.append(row)
    return result


def query_counts(repository, incidents, filters, now=None):
    now = now or datetime.now(timezone.utc)
    deadline = monotonic() + 25
    vessels = repository.insured_positions()
    events, offset = [], 0
    while True:
        if monotonic() > deadline:
            raise TimeoutError('Spatial batch deadline exceeded')
        rows, total = incidents.list(replace(filters, limit=1000, offset=offset), coordinates_only=True)
        if total > 50000:
            raise RuntimeError('Event batch too large; narrow filters')
        events.extend(rows)
        offset += len(rows)
        if offset >= total:
            break
        if not rows:
            raise RuntimeError('Incomplete event pagination')
    return {'items': calculate_counts(vessels, events, now), 'calculated_at': now.isoformat(),
            'radius_nm': RADIUS_NM, 'ais_max_age_hours': 24, 'time_basis': 'published_at_utc',
            'filters': {'from': filters.from_time, 'to': filters.to_time,
                        'incident_type': filters.incident_type, 'region': filters.region, 'status': filters.status}}

-- Phase 2.7.6: Service-role wrappers for route prediction persistence.
-- Purpose:
-- - Keep navigation.route_predictions in the private navigation schema.
-- - Let service-role repository calls access route predictions through tracking.

create or replace function tracking.get_active_route_prediction(p_mmsi text)
returns table (
    id uuid,
    vessel_id uuid,
    mmsi text,
    origin_position_id bigint,
    destination_raw text,
    destination_normalized text,
    destination_unlocode text,
    route_version integer,
    route_method text,
    route_geojson jsonb,
    great_circle_distance_nm double precision,
    navigable_distance_nm double precision,
    route_distance_ratio double precision,
    route_created_at timestamptz,
    route_update_reason text,
    status text,
    superseded_at timestamptz,
    request_id text,
    created_at timestamptz
)
language sql
stable
as $$
    select
        rp.id,
        rp.vessel_id,
        rp.mmsi,
        rp.origin_position_id,
        rp.destination_raw,
        rp.destination_normalized,
        rp.destination_unlocode,
        rp.route_version,
        rp.route_method,
        rp.route_geojson,
        rp.great_circle_distance_nm,
        rp.navigable_distance_nm,
        rp.route_distance_ratio,
        rp.route_created_at,
        rp.route_update_reason,
        rp.status,
        rp.superseded_at,
        rp.request_id,
        rp.created_at
    from navigation.route_predictions rp
    where rp.mmsi = nullif(trim(p_mmsi), '')
      and rp.status = 'active'
    order by rp.route_version desc
    limit 1;
$$;

create or replace function tracking.get_route_prediction(p_route_prediction_id uuid)
returns table (
    id uuid,
    vessel_id uuid,
    mmsi text,
    origin_position_id bigint,
    destination_raw text,
    destination_normalized text,
    destination_unlocode text,
    route_version integer,
    route_method text,
    route_geojson jsonb,
    great_circle_distance_nm double precision,
    navigable_distance_nm double precision,
    route_distance_ratio double precision,
    route_created_at timestamptz,
    route_update_reason text,
    status text,
    superseded_at timestamptz,
    request_id text,
    created_at timestamptz
)
language sql
stable
as $$
    select
        rp.id,
        rp.vessel_id,
        rp.mmsi,
        rp.origin_position_id,
        rp.destination_raw,
        rp.destination_normalized,
        rp.destination_unlocode,
        rp.route_version,
        rp.route_method,
        rp.route_geojson,
        rp.great_circle_distance_nm,
        rp.navigable_distance_nm,
        rp.route_distance_ratio,
        rp.route_created_at,
        rp.route_update_reason,
        rp.status,
        rp.superseded_at,
        rp.request_id,
        rp.created_at
    from navigation.route_predictions rp
    where rp.id = p_route_prediction_id
    limit 1;
$$;

create or replace function tracking.activate_route_prediction(
    p_vessel_id uuid,
    p_mmsi text,
    p_origin_position_id bigint,
    p_destination_raw text,
    p_destination_normalized text,
    p_destination_unlocode text,
    p_route_method text,
    p_route_geojson jsonb,
    p_great_circle_distance_nm double precision,
    p_navigable_distance_nm double precision,
    p_route_distance_ratio double precision,
    p_route_update_reason text,
    p_request_id text default null
)
returns table (
    route_prediction_id uuid,
    route_version integer,
    old_route_prediction_id uuid,
    inserted boolean
)
language sql
volatile
as $$
    select *
    from navigation.activate_route_prediction(
        p_vessel_id,
        p_mmsi,
        p_origin_position_id,
        p_destination_raw,
        p_destination_normalized,
        p_destination_unlocode,
        p_route_method,
        p_route_geojson,
        p_great_circle_distance_nm,
        p_navigable_distance_nm,
        p_route_distance_ratio,
        p_route_update_reason,
        p_request_id
    );
$$;

create or replace function tracking.supersede_route_prediction(
    p_route_prediction_id uuid
)
returns table (
    id uuid,
    status text,
    superseded_at timestamptz
)
language sql
volatile
as $$
    update navigation.route_predictions rp
    set status = 'superseded',
        superseded_at = now()
    where rp.id = p_route_prediction_id
      and rp.status = 'active'
    returning rp.id, rp.status, rp.superseded_at;
$$;

revoke all
on function tracking.get_active_route_prediction(text)
from public, anon, authenticated;

revoke all
on function tracking.get_route_prediction(uuid)
from public, anon, authenticated;

revoke all
on function tracking.activate_route_prediction(
    uuid,
    text,
    bigint,
    text,
    text,
    text,
    text,
    jsonb,
    double precision,
    double precision,
    double precision,
    text,
    text
)
from public, anon, authenticated;

revoke all
on function tracking.supersede_route_prediction(uuid)
from public, anon, authenticated;

grant execute
on function tracking.get_active_route_prediction(text)
to service_role;

grant execute
on function tracking.get_route_prediction(uuid)
to service_role;

grant execute
on function tracking.activate_route_prediction(
    uuid,
    text,
    bigint,
    text,
    text,
    text,
    text,
    jsonb,
    double precision,
    double precision,
    double precision,
    text,
    text
)
to service_role;

grant execute
on function tracking.supersede_route_prediction(uuid)
to service_role;

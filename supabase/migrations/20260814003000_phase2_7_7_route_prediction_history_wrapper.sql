-- Phase 2.7.7: Route prediction history wrapper.
-- Purpose:
-- - Keep navigation.route_predictions private.
-- - Expose service-role read access to route prediction history via tracking RPC.

create or replace function tracking.get_route_prediction_history(p_mmsi text)
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
    order by rp.route_version;
$$;

revoke all
on function tracking.get_route_prediction_history(text)
from public, anon, authenticated;

grant execute
on function tracking.get_route_prediction_history(text)
to service_role;

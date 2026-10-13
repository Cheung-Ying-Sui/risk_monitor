-- Reuse existing route history/activation; add a service-only guarded entrypoint.
-- Insurance association is an immutable GeoJSON foreign member, not a second route store.
create or replace function tracking.activate_insurance_route_prediction(p_snapshot jsonb)
returns table(route_prediction_id uuid, route_version integer, old_route_prediction_id uuid, inserted boolean)
language plpgsql security invoker
set search_path = pg_catalog, public, tracking, navigation, core
as $$
declare
    v core.vessels%rowtype;
    pos tracking.latest_vessel_positions%rowtype;
    ctx jsonb := p_snapshot->'route_geojson'->'insurance_voyage';
    expected jsonb;
    r record;
    n integer := 0;
begin
    select * into v from core.vessels where id=(p_snapshot->>'vessel_id')::uuid for update;
    if not found or v.mmsi is distinct from p_snapshot->>'mmsi'
        or ctx->>'vessel_id' is distinct from v.id::text
        or ctx->>'mmsi' is distinct from v.mmsi
        or ctx->>'destination_unlocode' is distinct from p_snapshot->>'destination_unlocode'
        or coalesce(jsonb_array_length(ctx->'shipments'),0)=0 then
        raise exception 'insurance route identity/context invalid' using errcode='22023';
    end if;
    if not exists(select 1 from tracking.tracked_vessels where vessel_id=v.id and is_active) then
        raise exception 'insurance vessel is not tracked' using errcode='40001';
    end if;
    select * into pos from tracking.latest_vessel_positions where vessel_id=v.id;
    if not found or pos.position_id is distinct from (p_snapshot->>'origin_position_id')::bigint
        or pos.observed_at < now()-interval '24 hours' or pos.observed_at > now()+interval '5 minutes'
        or pos.latitude not between -90 and 90 or pos.longitude not between -180 and 180
        or pos.latitude is null or pos.longitude is null or pos.observed_at is null then
        raise exception 'latest AIS changed or invalid' using errcode='40001';
    end if;
    for r in
        select s.id, s.declaration_id, s.discharge_port, s.etd
        from public.insurance_shipments s
        join public.insurance_declarations d on d.id=s.declaration_id
        join public.insurance_policies p on p.id=d.policy_id
        where d.status in ('confirmed','covered') and p.status<>'cancelled'
          and s.coverage_status is distinct from 'ended_by_mvp_departure'
          and s.extra_data->'voyage_lifecycle'->>'state' is distinct from 'ended'
          and ((nullif(trim(s.imo_number),'') is not null and trim(s.imo_number)=v.imo)
            or (nullif(trim(s.imo_number),'') is null and s.extra_data->>'mmsi_confirmed'='true'
                and s.extra_data->>'mmsi_candidate'=v.mmsi))
        order by s.id for share of s,d,p
    loop
        n := n+1;
        select value into expected from jsonb_array_elements(ctx->'shipments')
        where value->>'shipment_id'=r.id::text;
        if expected is null or expected->>'declaration_id' is distinct from r.declaration_id::text
            or expected->>'discharge_port' is distinct from r.discharge_port
            or (expected->>'etd')::timestamptz is distinct from r.etd then
            raise exception 'active insurance voyage changed' using errcode='40001';
        end if;
    end loop;
    if n=0 or n<>jsonb_array_length(ctx->'shipments') then
        raise exception 'insurance voyage ended or active set changed' using errcode='40001';
    end if;
    return query select * from navigation.activate_route_prediction(
        v.id, v.mmsi, pos.position_id, p_snapshot->>'destination_raw',
        p_snapshot->>'destination_normalized', p_snapshot->>'destination_unlocode',
        p_snapshot->>'route_method', p_snapshot->'route_geojson',
        (p_snapshot->>'great_circle_distance_nm')::double precision,
        (p_snapshot->>'navigable_distance_nm')::double precision,
        (p_snapshot->>'route_distance_ratio')::double precision,
        p_snapshot->>'route_update_reason', p_snapshot->>'request_id');
end;
$$;
revoke all on function tracking.activate_insurance_route_prediction(jsonb) from public, anon, authenticated;
grant execute on function tracking.activate_insurance_route_prediction(jsonb) to service_role;
notify pgrst, 'reload schema';

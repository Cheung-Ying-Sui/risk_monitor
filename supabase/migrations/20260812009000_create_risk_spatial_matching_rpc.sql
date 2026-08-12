-- Phase 2.6.1: Vessel-risk spatial matching RPC functions.
-- Purpose:
-- - Match current vessel positions against active risk zones in PostGIS.
-- - Record current tracked-vessel risk matches idempotently.

create or replace function risk.match_vessel_current_position(p_mmsi text)
returns table (
    vessel_id uuid,
    position_id bigint,
    mmsi text,
    latitude double precision,
    longitude double precision,
    observed_at timestamptz,
    zone_id uuid,
    zone_version_id uuid,
    zone_name text,
    zone_type text,
    source_document text,
    effective_date date
)
language sql
stable
as $$
    select
        lp.vessel_id,
        lp.position_id,
        lp.mmsi,
        lp.latitude,
        lp.longitude,
        lp.observed_at,
        az.zone_id,
        az.zone_version_id,
        az.zone_name,
        az.zone_type,
        az.source_document,
        az.effective_date
    from tracking.latest_vessel_positions lp
    join risk.active_zones az
        on lp.position is not null
       and st_intersects(
            az.geometry,
            lp.position::geometry
       )
    where lp.mmsi = p_mmsi;
$$;

create or replace function risk.match_tracked_vessels_current_positions()
returns table (
    tracked_vessel_id uuid,
    vessel_id uuid,
    position_id bigint,
    mmsi text,
    latitude double precision,
    longitude double precision,
    observed_at timestamptz,
    zone_id uuid,
    zone_version_id uuid,
    zone_name text,
    zone_type text,
    source_document text,
    effective_date date
)
language sql
stable
as $$
    select
        tv.id as tracked_vessel_id,
        lp.vessel_id,
        lp.position_id,
        lp.mmsi,
        lp.latitude,
        lp.longitude,
        lp.observed_at,
        az.zone_id,
        az.zone_version_id,
        az.zone_name,
        az.zone_type,
        az.source_document,
        az.effective_date
    from tracking.tracked_vessels tv
    join tracking.latest_vessel_positions lp
        on lp.vessel_id = tv.vessel_id
    join risk.active_zones az
        on lp.position is not null
       and st_intersects(
            az.geometry,
            lp.position::geometry
       )
    where tv.is_active = true;
$$;

create or replace function risk.record_current_tracked_vessel_risk_matches()
returns table (
    inserted_count bigint
)
language sql
volatile
as $$
    with inserted as (
        insert into risk.zone_matches (
            zone_id,
            zone_version_id,
            vessel_id,
            position_id,
            mmsi,
            matched_at,
            observed_at,
            match_type,
            alert_status,
            created_at
        )
        select
            matches.zone_id,
            matches.zone_version_id,
            matches.vessel_id,
            matches.position_id,
            matches.mmsi,
            now(),
            matches.observed_at,
            'intersects',
            'new',
            now()
        from risk.match_tracked_vessels_current_positions() matches
        on conflict (position_id, zone_version_id, match_type)
        do nothing
        returning 1
    )
    select count(*)::bigint as inserted_count
    from inserted;
$$;

grant execute
on function risk.match_vessel_current_position(text)
to service_role;

grant execute
on function risk.match_tracked_vessels_current_positions()
to service_role;

grant execute
on function risk.record_current_tracked_vessel_risk_matches()
to service_role;

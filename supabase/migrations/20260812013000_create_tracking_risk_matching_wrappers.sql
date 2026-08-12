-- Phase 2.6.4: Service-role wrappers for risk matching RPCs.
-- Purpose:
-- - Keep the private risk schema out of the exposed Data API schema list.
-- - Let service-role jobs call risk matching through the exposed tracking schema.

create or replace function tracking.get_active_risk_zones()
returns table (
    zone_id uuid,
    zone_version_id uuid,
    zone_name text,
    zone_slug text,
    zone_type text,
    source text,
    source_document text,
    effective_date date,
    confidence numeric
)
language sql
stable
as $$
    select
        az.zone_id,
        az.zone_version_id,
        az.zone_name,
        az.zone_slug,
        az.zone_type,
        az.source,
        az.source_document,
        az.effective_date,
        az.confidence
    from risk.active_zones az
    order by az.zone_name;
$$;

create or replace function tracking.match_vessel_current_position(p_mmsi text)
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
    select *
    from risk.match_vessel_current_position(p_mmsi);
$$;

create or replace function tracking.match_tracked_vessels_current_positions()
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
    select *
    from risk.match_tracked_vessels_current_positions();
$$;

create or replace function tracking.record_current_tracked_vessel_risk_matches()
returns table (
    inserted_count bigint
)
language sql
volatile
as $$
    select *
    from risk.record_current_tracked_vessel_risk_matches();
$$;

revoke all
on function tracking.get_active_risk_zones()
from public, anon, authenticated;

revoke all
on function tracking.match_vessel_current_position(text)
from public, anon, authenticated;

revoke all
on function tracking.match_tracked_vessels_current_positions()
from public, anon, authenticated;

revoke all
on function tracking.record_current_tracked_vessel_risk_matches()
from public, anon, authenticated;

grant execute
on function tracking.get_active_risk_zones()
to service_role;

grant execute
on function tracking.match_vessel_current_position(text)
to service_role;

grant execute
on function tracking.match_tracked_vessels_current_positions()
to service_role;

grant execute
on function tracking.record_current_tracked_vessel_risk_matches()
to service_role;

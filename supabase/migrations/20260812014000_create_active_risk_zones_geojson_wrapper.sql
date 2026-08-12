-- Phase 2.6.8: Active risk zones GeoJSON wrapper.
-- Purpose:
-- - Keep the private risk schema out of the exposed Data API schema list.
-- - Let service-role Dashboard calls read active risk zone GeoJSON.
-- - Do not duplicate spatial matching or GeoJSON generation logic.

create or replace function tracking.get_active_risk_zones_geojson()
returns table (
    zone_id uuid,
    zone_version_id uuid,
    zone_name text,
    zone_type text,
    source text,
    source_document text,
    effective_date date,
    geometry_geojson jsonb
)
language sql
stable
as $$
    select
        az.zone_id,
        az.zone_version_id,
        az.zone_name,
        az.zone_type,
        az.source,
        az.source_document,
        az.effective_date,
        az.geometry_geojson
    from risk.active_zones_geojson az
    order by az.zone_name;
$$;

revoke all
on function tracking.get_active_risk_zones_geojson()
from public, anon, authenticated;

grant execute
on function tracking.get_active_risk_zones_geojson()
to service_role;

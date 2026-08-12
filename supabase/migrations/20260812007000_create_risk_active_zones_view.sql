-- Phase 2.5.4.3.4: Active risk zone query views.
-- Purpose:
-- - Provide active risk zones for spatial matching.
-- - Provide row-level GeoJSON geometry for map clients without replacing the geometry view.

create or replace view risk.active_zones as
select
    z.id as zone_id,
    zv.id as zone_version_id,
    z.zone_name,
    z.zone_slug,
    z.zone_type,
    z.source,
    zs.source_document,
    zs.source_url,
    zs.document_hash,
    zv.effective_date,
    zv.geometry,
    zv.confidence,
    zv.raw_text,
    zv.created_at,
    zv.activated_at
from risk.zone_versions zv
join risk.zones z
    on z.id = zv.zone_id
join risk.zone_sources zs
    on zs.id = zv.source_id
where zv.status = 'active'
  and z.status = 'active';

create or replace view risk.active_zones_geojson as
select
    zone_id,
    zone_version_id,
    zone_name,
    zone_slug,
    zone_type,
    source,
    source_document,
    source_url,
    document_hash,
    effective_date,
    confidence,
    raw_text,
    created_at,
    activated_at,
    st_asgeojson(geometry)::jsonb as geometry_geojson
from risk.active_zones;

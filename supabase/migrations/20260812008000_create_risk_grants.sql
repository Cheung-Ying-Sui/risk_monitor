-- Phase 2.5.4.3.4: Risk schema service role grants.
-- Purpose:
-- - Allow Supabase service_role to access risk zone tables and views.
-- - Do not grant anon or authenticated access.

grant usage on schema risk to service_role;

grant select, insert, update
on table risk.zone_sources
to service_role;

grant select, insert, update
on table risk.zones
to service_role;

grant select, insert, update
on table risk.zone_versions
to service_role;

grant select, insert, update
on table risk.zone_matches
to service_role;

grant select
on table risk.active_zones
to service_role;

grant select
on table risk.active_zones_geojson
to service_role;

grant usage, select
on all sequences in schema risk
to service_role;

-- Phase 2.5.2.4.3: Grants for latest vessel positions view.
-- Purpose:
-- - Allow Supabase service_role to query latest vessel positions through the Data API.

grant usage on schema tracking to service_role;

grant select
on table tracking.latest_vessel_positions
to service_role;

grant select
on table tracking.vessel_positions
to service_role;

grant select
on table tracking.tracked_vessels
to service_role;

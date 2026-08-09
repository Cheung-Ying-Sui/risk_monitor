-- Phase 2.5.2.3.3: Grants for collection run audit tables.
-- Purpose:
-- - Allow Supabase service_role to access ingest collection log tables.

grant usage on schema ingest to service_role;

grant select, insert, update
on table ingest.collection_runs
to service_role;

grant select, insert, update
on table ingest.collection_run_items
to service_role;

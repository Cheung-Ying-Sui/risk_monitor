-- Phase 2.5.2.2: Collection run audit logs.
-- Purpose:
-- - Record each scheduled or manual vessel collection job run.
-- - Record per-vessel collection results for audit and troubleshooting.

create extension if not exists pgcrypto;

create schema if not exists ingest;

create table if not exists ingest.collection_runs (
    id uuid primary key default gen_random_uuid(),
    started_at timestamptz not null,
    finished_at timestamptz,
    status text,
    trigger_source text,
    total_vessels integer,
    success_count integer,
    failed_count integer,
    created_at timestamptz not null default now()
);

create table if not exists ingest.collection_run_items (
    id uuid primary key default gen_random_uuid(),
    run_id uuid references ingest.collection_runs(id),
    mmsi text not null,
    status text,
    error_message text,
    started_at timestamptz,
    finished_at timestamptz,
    created_at timestamptz not null default now()
);

create index if not exists idx_ingest_collection_runs_created_at
on ingest.collection_runs (created_at);

create index if not exists idx_ingest_collection_run_items_run_id
on ingest.collection_run_items (run_id);

create index if not exists idx_ingest_collection_run_items_mmsi
on ingest.collection_run_items (mmsi);

create index if not exists idx_ingest_collection_run_items_created_at
on ingest.collection_run_items (created_at);

comment on table ingest.collection_runs is
'Audit table for each vessel collection job run.';

comment on column ingest.collection_runs.started_at is
'Timestamp when the collection job started.';

comment on column ingest.collection_runs.finished_at is
'Timestamp when the collection job finished.';

comment on column ingest.collection_runs.status is
'Overall job status, such as running, success, partial_failed, or failed.';

comment on column ingest.collection_runs.trigger_source is
'Source that triggered the job, such as github_actions_schedule, workflow_dispatch, or local_manual.';

comment on column ingest.collection_runs.total_vessels is
'Number of vessels selected for collection in this run.';

comment on column ingest.collection_runs.success_count is
'Number of vessels collected successfully in this run.';

comment on column ingest.collection_runs.failed_count is
'Number of vessels that failed collection in this run.';

comment on table ingest.collection_run_items is
'Per-vessel audit table for collection job results.';

comment on column ingest.collection_run_items.run_id is
'Collection run identifier from ingest.collection_runs.';

comment on column ingest.collection_run_items.mmsi is
'MMSI collected during the run.';

comment on column ingest.collection_run_items.status is
'Per-vessel collection status, such as success, skipped, or failed.';

comment on column ingest.collection_run_items.error_message is
'Error message captured when per-vessel collection fails.';

comment on column ingest.collection_run_items.started_at is
'Timestamp when this vessel collection attempt started.';

comment on column ingest.collection_run_items.finished_at is
'Timestamp when this vessel collection attempt finished.';

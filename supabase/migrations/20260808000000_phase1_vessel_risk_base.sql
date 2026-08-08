-- Phase 1: Vessel risk database foundation for Supabase PostgreSQL
-- Purpose:
-- - Replace legacy "Marine Risk".vessel_static with core.vessels
-- - Replace legacy "Marine Risk".vessel_dynamic with tracking.vessel_positions
-- - Add tracking.tracked_vessels for scheduled collection targets
-- - Add ingest.data_sources for source governance

create extension if not exists pgcrypto;
create extension if not exists postgis;

create schema if not exists core;
create schema if not exists tracking;
create schema if not exists ingest;

create or replace function core.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create or replace function tracking.set_position_from_lat_lon()
returns trigger
language plpgsql
as $$
begin
    if new.latitude is not null and new.longitude is not null then
        new.position = st_setsrid(
            st_makepoint(new.longitude, new.latitude),
            4326
        )::geography;
    else
        new.position = null;
    end if;

    return new;
end;
$$;

create table if not exists core.vessels (
    id uuid primary key default gen_random_uuid(),
    mmsi text unique not null,
    imo text,
    ship_name text,
    callsign text,
    ship_type text,
    flag_state text,
    length_m numeric,
    width_m numeric,
    gross_tonnage numeric,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

drop trigger if exists trg_core_vessels_set_updated_at on core.vessels;

create trigger trg_core_vessels_set_updated_at
before update on core.vessels
for each row
execute function core.set_updated_at();

create table if not exists ingest.data_sources (
    id uuid primary key default gen_random_uuid(),
    source_code text unique not null,
    source_name text,
    source_type text,
    created_at timestamptz not null default now()
);

create table if not exists tracking.vessel_positions (
    id bigint generated always as identity primary key,
    vessel_id uuid references core.vessels(id),
    mmsi text,
    latitude double precision,
    longitude double precision,
    position geography(Point, 4326),
    sog numeric,
    cog numeric,
    heading numeric,
    destination text,
    nav_status text,
    observed_at timestamptz,
    received_at timestamptz not null default now(),
    created_at timestamptz not null default now()
);

drop trigger if exists trg_tracking_vessel_positions_set_position on tracking.vessel_positions;

create trigger trg_tracking_vessel_positions_set_position
before insert or update of latitude, longitude on tracking.vessel_positions
for each row
execute function tracking.set_position_from_lat_lon();

create table if not exists tracking.tracked_vessels (
    id uuid primary key default gen_random_uuid(),
    vessel_id uuid references core.vessels(id),
    mmsi text,
    is_active boolean not null default true,
    priority integer not null default 0,
    tracking_interval_minutes integer not null default 10,
    created_at timestamptz not null default now()
);

create index if not exists idx_core_vessels_mmsi
on core.vessels (mmsi);

create index if not exists idx_core_vessels_imo
on core.vessels (imo)
where imo is not null;

create index if not exists idx_tracking_vessel_positions_vessel_observed_at_desc
on tracking.vessel_positions (vessel_id, observed_at desc);

create index if not exists idx_tracking_vessel_positions_mmsi_observed_at_desc
on tracking.vessel_positions (mmsi, observed_at desc);

create index if not exists idx_tracking_vessel_positions_position_gist
on tracking.vessel_positions
using gist (position);

create index if not exists idx_tracking_tracked_vessels_vessel_id
on tracking.tracked_vessels (vessel_id);

create index if not exists idx_tracking_tracked_vessels_active_priority
on tracking.tracked_vessels (is_active, priority desc, created_at);

create index if not exists idx_tracking_tracked_vessels_mmsi
on tracking.tracked_vessels (mmsi);

insert into ingest.data_sources (
    source_code,
    source_name,
    source_type
)
values
    ('CHINAPORTS', 'Chinaports Ship Information API', 'api'),
    ('MANUAL', 'Manual Input', 'manual')
on conflict (source_code) do update set
    source_name = excluded.source_name,
    source_type = excluded.source_type;

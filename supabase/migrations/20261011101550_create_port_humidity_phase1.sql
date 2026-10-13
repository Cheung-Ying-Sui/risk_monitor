-- Phase 1 humidity data. No port-city coordinates are seeded as terminal coordinates.
create table public.weather_ports (
    id uuid primary key default gen_random_uuid(),
    port_code text not null unique,
    name_zh text not null,
    region_zh text not null,
    unlocode text,
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint weather_ports_code_check check (port_code ~ '^CN_[A-Z]+$')
);

create table public.port_weather_locations (
    id uuid primary key default gen_random_uuid(),
    port_id uuid not null references public.weather_ports(id) on delete restrict,
    name text not null,
    requested_latitude double precision,
    requested_longitude double precision,
    coordinate_source text,
    verification_status text not null default 'pending_verification'
        check (verification_status in ('pending_verification', 'verified', 'rejected')),
    verified_at timestamptz,
    location_description text,
    timezone text not null default 'Asia/Shanghai',
    is_primary boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint port_weather_location_lat_check check (requested_latitude between -90 and 90 or requested_latitude is null),
    constraint port_weather_location_lon_check check (requested_longitude between -180 and 180 or requested_longitude is null),
    constraint port_weather_location_verified_check check (
        verification_status <> 'verified' or
        (requested_latitude is not null and requested_longitude is not null and
         nullif(trim(coordinate_source), '') is not null and verified_at is not null and
         nullif(trim(location_description), '') is not null)
    ),
    constraint port_weather_location_primary_check check (not is_primary or verification_status = 'verified')
);
create unique index port_weather_locations_one_primary
    on public.port_weather_locations(port_id) where is_primary;
create index port_weather_locations_port_idx on public.port_weather_locations(port_id);

create table public.weather_data_sources (
    id uuid primary key default gen_random_uuid(),
    provider text not null,
    dataset text not null,
    api_endpoint text not null,
    model_options jsonb not null default '{}'::jsonb,
    documentation_url text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (provider, dataset, api_endpoint)
);

create table public.weather_ingestion_batches (
    id uuid primary key default gen_random_uuid(),
    weather_location_id uuid not null references public.port_weather_locations(id) on delete restrict,
    source_id uuid not null references public.weather_data_sources(id) on delete restrict,
    start_date date not null,
    end_date date not null,
    status text not null default 'pending' check (status in ('pending', 'running', 'succeeded', 'failed', 'partial')),
    expected_hours integer not null default 0,
    received_hours integer not null default 0,
    upserted_rows integer not null default 0,
    null_rh_rows integer not null default 0,
    missing_hours integer not null default 0,
    duplicate_hours integer not null default 0,
    requested_grid_latitude double precision,
    requested_grid_longitude double precision,
    response_grid_latitude double precision,
    response_grid_longitude double precision,
    response_elevation_m double precision,
    response_timezone text,
    response_utc_offset_seconds integer,
    hourly_units jsonb,
    request_params jsonb not null default '{}'::jsonb,
    response_sha256 text,
    attempts integer not null default 0,
    error_summary text,
    started_at timestamptz,
    finished_at timestamptz,
    created_at timestamptz not null default now(),
    constraint weather_batch_dates_check check (end_date >= start_date),
    constraint weather_batch_counts_check check (
        expected_hours >= 0 and received_hours >= 0 and upserted_rows >= 0 and
        null_rh_rows >= 0 and missing_hours >= 0 and duplicate_hours >= 0 and attempts >= 0
    )
);
create index weather_batches_resume_idx
    on public.weather_ingestion_batches(weather_location_id, source_id, start_date, end_date, created_at desc);
create index weather_batches_status_idx
    on public.weather_ingestion_batches(status, created_at desc);

create table public.port_weather_hourly (
    id bigint generated always as identity primary key,
    weather_location_id uuid not null references public.port_weather_locations(id) on delete restrict,
    source_id uuid not null references public.weather_data_sources(id) on delete restrict,
    observed_at_utc timestamptz not null,
    relative_humidity_pct double precision,
    temperature_2m_c double precision,
    dew_point_2m_c double precision,
    precipitation_mm double precision,
    grid_latitude double precision,
    grid_longitude double precision,
    grid_elevation_m double precision,
    ingested_at timestamptz not null default now(),
    batch_id uuid references public.weather_ingestion_batches(id) on delete restrict,
    unique (weather_location_id, source_id, observed_at_utc),
    constraint weather_hourly_utc_hour_check check (
        extract(minute from observed_at_utc) = 0 and extract(second from observed_at_utc) = 0
    ),
    constraint weather_hourly_rh_check check (relative_humidity_pct between 0 and 100 or relative_humidity_pct is null),
    constraint weather_hourly_precip_check check (precipitation_mm >= 0 or precipitation_mm is null),
    constraint weather_hourly_grid_lat_check check (grid_latitude between -90 and 90 or grid_latitude is null),
    constraint weather_hourly_grid_lon_check check (grid_longitude between -180 and 180 or grid_longitude is null)
);
create index weather_hourly_location_time_idx
    on public.port_weather_hourly(weather_location_id, observed_at_utc);

create table public.weather_data_quality_reports (
    id uuid primary key default gen_random_uuid(),
    weather_location_id uuid not null references public.port_weather_locations(id) on delete restrict,
    source_id uuid not null references public.weather_data_sources(id) on delete restrict,
    batch_id uuid references public.weather_ingestion_batches(id) on delete restrict,
    period_start_utc timestamptz not null,
    period_end_utc timestamptz not null,
    generated_at timestamptz not null default now(),
    expected_hours integer not null,
    actual_distinct_hours integer not null,
    complete_row_hours integer not null,
    missing_hours integer not null,
    null_rh_hours integer not null,
    invalid_value_hours integer not null,
    completeness_ratio numeric(8,6) not null,
    rh_valid_ratio numeric(8,6) not null,
    status text not null check (status in ('pass', 'warn', 'fail')),
    details jsonb not null default '{}'::jsonb,
    constraint weather_quality_period_check check (period_end_utc > period_start_utc),
    constraint weather_quality_ratio_check check (
        completeness_ratio between 0 and 1 and rh_valid_ratio between 0 and 1
    )
);
create index weather_quality_location_period_idx
    on public.weather_data_quality_reports(weather_location_id, period_start_utc, generated_at desc);

alter table public.weather_ports enable row level security;
alter table public.port_weather_locations enable row level security;
alter table public.weather_data_sources enable row level security;
alter table public.weather_ingestion_batches enable row level security;
alter table public.port_weather_hourly enable row level security;
alter table public.weather_data_quality_reports enable row level security;

revoke all on public.weather_ports, public.port_weather_locations, public.weather_data_sources,
    public.weather_ingestion_batches, public.port_weather_hourly, public.weather_data_quality_reports
    from public, anon, authenticated;
grant select, insert, update on public.weather_ports, public.port_weather_locations,
    public.weather_data_sources, public.weather_ingestion_batches, public.port_weather_hourly,
    public.weather_data_quality_reports to service_role;
grant usage, select on sequence public.port_weather_hourly_id_seq to service_role;

comment on table public.port_weather_hourly is 'Open-Meteo ERA5 hourly values in UTC; precipitation is the preceding-hour sum.';
comment on column public.port_weather_hourly.precipitation_mm is 'Previous hour accumulated precipitation in mm, not an instantaneous value.';

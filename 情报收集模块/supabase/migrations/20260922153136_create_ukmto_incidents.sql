begin;

create table public.ukmto_incidents (
    id uuid primary key default gen_random_uuid(),
    source text not null default 'UKMTO' check (source = 'UKMTO'),
    external_id text not null check (length(external_id) > 0),
    incident_number text,
    incident_type text not null check (incident_type in
        ('attack', 'suspicious_activity', 'hijack', 'advisory', 'military_interaction', 'unknown')),
    title text,
    description text,
    incident_time timestamptz,
    published_at timestamptz,
    source_updated_at timestamptz,
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    location_text text,
    latitude double precision check (latitude between -90 and 90),
    longitude double precision check (longitude between -180 and 180),
    location_precision text check (location_precision in ('exact', 'approximate', 'region', 'unknown')),
    region text,
    vessel_type text,
    source_type text,
    verification_status text,
    casualties text,
    environmental_impact text,
    source_url text not null,
    content_hash text not null check (content_hash ~ '^[a-f0-9]{64}$'),
    raw_payload jsonb,
    status text not null default 'active',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uk_ukmto_incidents_external_id unique (source, external_id),
    constraint ukmto_coordinate_pair check ((latitude is null) = (longitude is null))
);

create table public.ukmto_incident_updates (
    id uuid primary key default gen_random_uuid(),
    incident_id uuid not null references public.ukmto_incidents(id) on delete cascade,
    content_hash text not null,
    title text,
    description text,
    incident_type text,
    incident_time timestamptz,
    published_at timestamptz,
    location_text text,
    latitude double precision,
    longitude double precision,
    raw_payload jsonb,
    observed_at timestamptz not null default now(),
    constraint uk_ukmto_incident_updates_hash unique (incident_id, content_hash)
);

create index idx_ukmto_incidents_published_at on public.ukmto_incidents (published_at desc);
create index idx_ukmto_incidents_incident_time on public.ukmto_incidents (incident_time desc);
create index idx_ukmto_incidents_type on public.ukmto_incidents (incident_type);
create index idx_ukmto_incidents_region on public.ukmto_incidents (region);
create index idx_ukmto_incidents_lat_lon on public.ukmto_incidents (latitude, longitude);
-- The history unique index already covers the incident_id foreign key.

alter table public.ukmto_incidents enable row level security;
alter table public.ukmto_incident_updates enable row level security;
revoke all on public.ukmto_incidents, public.ukmto_incident_updates from public, anon, authenticated;
grant select, insert, update on public.ukmto_incidents to service_role;
grant select, insert on public.ukmto_incident_updates to service_role;

-- One RPC = one transaction. A conflicting INSERT waits for the other writer;
-- SELECT FOR UPDATE then serializes comparisons of the current version.
create function public.ingest_ukmto_incident(p_incident jsonb, p_observed_at timestamptz)
returns text
language plpgsql
security invoker
set search_path = ''
as $$
declare
    incoming public.ukmto_incidents%rowtype;
    current_row public.ukmto_incidents%rowtype;
    incident_id uuid;
    action text;
    stale boolean;
begin
    if p_observed_at is null then
        raise exception 'p_observed_at is required';
    end if;
    incoming := jsonb_populate_record(null::public.ukmto_incidents, p_incident);
    if incoming.source is distinct from 'UKMTO' then
        raise exception 'source must be UKMTO';
    end if;
    insert into public.ukmto_incidents (
        source, external_id, incident_number, incident_type, title, description,
        incident_time, published_at, source_updated_at, first_seen_at, last_seen_at,
        location_text, latitude, longitude, location_precision, region, vessel_type,
        source_type, verification_status, casualties, environmental_impact,
        source_url, content_hash, raw_payload, status
    ) values (
        incoming.source, incoming.external_id, incoming.incident_number, incoming.incident_type,
        incoming.title, incoming.description, incoming.incident_time, incoming.published_at,
        incoming.source_updated_at, p_observed_at, p_observed_at, incoming.location_text,
        incoming.latitude, incoming.longitude, incoming.location_precision, incoming.region,
        incoming.vessel_type, incoming.source_type, incoming.verification_status,
        incoming.casualties, incoming.environmental_impact, incoming.source_url,
        incoming.content_hash, incoming.raw_payload, coalesce(incoming.status, 'active')
    ) on conflict (source, external_id) do nothing
    returning id into incident_id;

    if incident_id is not null then
        action := 'inserted';
    else
        select * into strict current_row from public.ukmto_incidents
        where source = incoming.source and external_id = incoming.external_id for update;
        incident_id := current_row.id;
        stale := p_observed_at < current_row.last_seen_at
            or coalesce(incoming.source_updated_at, incoming.published_at)
                < coalesce(current_row.source_updated_at, current_row.published_at)
            or coalesce((incoming.raw_payload->>'update_number')::integer, 0)
                < coalesce((current_row.raw_payload->>'update_number')::integer, 0);
        if current_row.content_hash = incoming.content_hash or coalesce(stale, false) then
            update public.ukmto_incidents set last_seen_at = greatest(last_seen_at, p_observed_at)
            where id = incident_id;
            action := 'unchanged';
        else
            update public.ukmto_incidents set
                incident_number = incoming.incident_number,
                incident_type = incoming.incident_type,
                title = incoming.title,
                description = incoming.description,
                incident_time = incoming.incident_time,
                published_at = incoming.published_at,
                source_updated_at = incoming.source_updated_at,
                last_seen_at = greatest(last_seen_at, p_observed_at),
                location_text = incoming.location_text,
                latitude = incoming.latitude,
                longitude = incoming.longitude,
                location_precision = incoming.location_precision,
                region = incoming.region,
                vessel_type = incoming.vessel_type,
                source_type = incoming.source_type,
                verification_status = incoming.verification_status,
                casualties = incoming.casualties,
                environmental_impact = incoming.environmental_impact,
                source_url = incoming.source_url,
                content_hash = incoming.content_hash,
                raw_payload = incoming.raw_payload,
                status = coalesce(incoming.status, 'active'),
                updated_at = clock_timestamp()
            where id = incident_id;
            action := 'updated';
        end if;
    end if;

    -- Historical/late versions are retained even if they must not replace the latest version.
    insert into public.ukmto_incident_updates (
        incident_id, content_hash, title, description, incident_type, incident_time,
        published_at, location_text, latitude, longitude, raw_payload, observed_at
    ) values (
        incident_id, incoming.content_hash, incoming.title, incoming.description,
        incoming.incident_type, incoming.incident_time, incoming.published_at,
        incoming.location_text, incoming.latitude, incoming.longitude,
        jsonb_build_object('snapshot', p_incident, 'source_payload', incoming.raw_payload), p_observed_at
    ) on conflict on constraint uk_ukmto_incident_updates_hash do nothing;
    return action;
end;
$$;

revoke all on function public.ingest_ukmto_incident(jsonb, timestamptz) from public, anon, authenticated;
grant execute on function public.ingest_ukmto_incident(jsonb, timestamptz) to service_role;

comment on table public.ukmto_incidents is 'UKMTO incident reports, not live AIS vessel positions. Crown copyright; retain source attribution.';
commit;

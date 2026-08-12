-- Phase 2.5.4.3.4: Risk zone geometry versions.
-- Purpose:
-- - Store versioned PostGIS geometries derived from source documents.
-- - Enforce one active version per stable risk zone.

create table if not exists risk.zone_versions (
    id uuid primary key default gen_random_uuid(),
    zone_id uuid not null references risk.zones(id),
    source_id uuid not null references risk.zone_sources(id),
    version_no integer not null,
    effective_date date,
    geometry geometry(MultiPolygon, 4326) not null,
    raw_text text,
    raw_extraction jsonb,
    iho_matches jsonb,
    validation_result jsonb,
    confidence numeric,
    status text not null default 'draft',
    created_at timestamptz not null default now(),
    activated_at timestamptz,
    superseded_at timestamptz,
    constraint zone_versions_zone_version_no_unique unique (zone_id, version_no),
    constraint zone_versions_confidence_check check (
        confidence is null
        or (
            confidence >= 0
            and confidence <= 1
        )
    ),
    constraint zone_versions_status_check check (
        status in (
            'draft',
            'validated',
            'active',
            'superseded',
            'needs_review',
            'rejected'
        )
    )
);

create index if not exists idx_risk_zone_versions_geometry_gist
on risk.zone_versions
using gist (geometry);

create index if not exists idx_risk_zone_versions_zone_status
on risk.zone_versions (zone_id, status);

create index if not exists idx_risk_zone_versions_source_id
on risk.zone_versions (source_id);

create index if not exists idx_risk_zone_versions_effective_date_desc
on risk.zone_versions (effective_date desc);

create index if not exists idx_risk_zone_versions_status
on risk.zone_versions (status);

create unique index if not exists idx_risk_zone_versions_one_active_per_zone
on risk.zone_versions (zone_id)
where status = 'active';

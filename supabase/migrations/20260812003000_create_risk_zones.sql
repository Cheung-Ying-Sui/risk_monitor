-- Phase 2.5.4.3.4: Risk zone stable identities.
-- Purpose:
-- - Store stable business identities for risk zones across source document versions.

create table if not exists risk.zones (
    id uuid primary key default gen_random_uuid(),
    zone_name text not null,
    zone_slug text not null,
    zone_type text not null,
    source text not null,
    description text,
    status text not null default 'draft',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint zones_source_zone_slug_unique unique (source, zone_slug),
    constraint zones_zone_type_check check (
        zone_type in (
            'maritime',
            'country',
            'coastal_area',
            'custom_boundary'
        )
    ),
    constraint zones_status_check check (
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

create index if not exists idx_risk_zones_source_status
on risk.zones (source, status);

create index if not exists idx_risk_zones_zone_type
on risk.zones (zone_type);

create index if not exists idx_risk_zones_zone_slug
on risk.zones (zone_slug);

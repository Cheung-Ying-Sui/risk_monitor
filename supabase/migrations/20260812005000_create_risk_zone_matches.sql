-- Phase 2.5.4.3.4: Vessel risk zone match records.
-- Purpose:
-- - Store auditable vessel-position-to-risk-zone spatial matches.

create table if not exists risk.zone_matches (
    id bigint generated always as identity primary key,
    zone_id uuid not null references risk.zones(id),
    zone_version_id uuid not null references risk.zone_versions(id),
    vessel_id uuid references core.vessels(id),
    position_id bigint not null references tracking.vessel_positions(id),
    mmsi text not null,
    matched_at timestamptz not null default now(),
    observed_at timestamptz not null,
    match_type text not null,
    distance_to_boundary_m numeric,
    alert_status text not null default 'new',
    created_at timestamptz not null default now(),
    constraint zone_matches_position_version_match_type_unique unique (
        position_id,
        zone_version_id,
        match_type
    ),
    constraint zone_matches_match_type_check check (
        match_type in (
            'intersects',
            'near_boundary'
        )
    ),
    constraint zone_matches_alert_status_check check (
        alert_status in (
            'new',
            'notified',
            'acknowledged',
            'resolved'
        )
    )
);

create index if not exists idx_risk_zone_matches_mmsi_observed_at_desc
on risk.zone_matches (mmsi, observed_at desc);

create index if not exists idx_risk_zone_matches_vessel_observed_at_desc
on risk.zone_matches (vessel_id, observed_at desc);

create index if not exists idx_risk_zone_matches_zone_observed_at_desc
on risk.zone_matches (zone_id, observed_at desc);

create index if not exists idx_risk_zone_matches_zone_version_id
on risk.zone_matches (zone_version_id);

create index if not exists idx_risk_zone_matches_alert_status
on risk.zone_matches (alert_status);

create index if not exists idx_risk_zone_matches_matched_at_desc
on risk.zone_matches (matched_at desc);

-- Phase 2.5.4.3.4: JWLA risk zone source documents.
-- Purpose:
-- - Store source document metadata and extracted text for risk zone ingestion.
-- - Deduplicate documents by source and document content hash.

create table if not exists risk.zone_sources (
    id uuid primary key default gen_random_uuid(),
    source text not null,
    source_url text not null,
    source_document text,
    document_hash text not null,
    document_date date,
    fetched_at timestamptz not null default now(),
    raw_text text,
    parser_version text,
    status text not null default 'draft',
    error_message text,
    created_at timestamptz not null default now(),
    constraint zone_sources_source_document_hash_unique unique (source, document_hash),
    constraint zone_sources_status_check check (
        status in (
            'draft',
            'validated',
            'active',
            'needs_review',
            'rejected'
        )
    )
);

create index if not exists idx_risk_zone_sources_source_document_date_desc
on risk.zone_sources (source, document_date desc);

create index if not exists idx_risk_zone_sources_status
on risk.zone_sources (status);

create index if not exists idx_risk_zone_sources_created_at_desc
on risk.zone_sources (created_at desc);

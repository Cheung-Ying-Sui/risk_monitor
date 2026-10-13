-- Marine cargo insurance management backend.
-- Creates the Policy -> Declaration -> Shipment -> Document model and a
-- confirmation-safe declaration import workflow. All access is server-side
-- through service_role; anon/authenticated receive no direct table access.

create extension if not exists pgcrypto;

create table public.insurance_companies (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    name_en text,
    aliases text[] not null default '{}',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint insurance_companies_name_not_blank check (length(trim(name)) > 0)
);

create unique index insurance_companies_name_unique
on public.insurance_companies (lower(name));

create table public.insurance_policies (
    id uuid primary key default gen_random_uuid(),
    company_id uuid not null references public.insurance_companies(id) on delete restrict,
    policy_name text not null,
    policy_number text not null,
    insurer text not null,
    start_date date not null,
    end_date date not null,
    currency text not null default 'USD',
    rate numeric(12, 8),
    shipment_limit numeric(20, 2),
    annual_estimated_value numeric(20, 2),
    valuation_basis text,
    deductible text,
    cargo_scope text,
    territory text,
    transport_mode text,
    insurance_clause text,
    war_risk text,
    special_conditions text,
    status text not null default 'active',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint insurance_policies_name_not_blank check (length(trim(policy_name)) > 0),
    constraint insurance_policies_number_not_blank check (length(trim(policy_number)) > 0),
    constraint insurance_policies_insurer_not_blank check (length(trim(insurer)) > 0),
    constraint insurance_policies_dates_valid check (end_date >= start_date),
    constraint insurance_policies_currency_valid check (currency ~ '^[A-Z]{3}$'),
    constraint insurance_policies_rate_nonnegative check (rate is null or rate >= 0),
    constraint insurance_policies_shipment_limit_nonnegative check (shipment_limit is null or shipment_limit >= 0),
    constraint insurance_policies_annual_value_nonnegative check (annual_estimated_value is null or annual_estimated_value >= 0),
    constraint insurance_policies_status_valid check (status in ('active', 'pending', 'cancelled'))
);

create unique index insurance_policies_company_number_unique
on public.insurance_policies (company_id, lower(policy_number));

create index insurance_policies_company_id_idx
on public.insurance_policies (company_id);

create index insurance_policies_dates_idx
on public.insurance_policies (start_date, end_date);

create index insurance_policies_insurer_idx
on public.insurance_policies (lower(insurer));

create table public.insurance_declaration_imports (
    id uuid primary key default gen_random_uuid(),
    policy_id uuid not null references public.insurance_policies(id) on delete restrict,
    company_id uuid not null references public.insurance_companies(id) on delete restrict,
    source_type text not null default 'manual_upload',
    source_file_name text not null,
    content_type text,
    file_size bigint not null,
    storage_bucket text not null,
    storage_path text not null,
    file_sha256 text not null,
    parser_name text not null,
    parser_version text not null,
    parsed_data jsonb not null,
    parse_warnings jsonb not null default '[]'::jsonb,
    status text not null default 'pending_confirmation',
    confirmed_declaration_id uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint insurance_declaration_imports_source_valid check (source_type in ('manual_upload', 'email', 'api')),
    constraint insurance_declaration_imports_size_valid check (file_size >= 0),
    constraint insurance_declaration_imports_hash_valid check (file_sha256 ~ '^[0-9a-f]{64}$'),
    constraint insurance_declaration_imports_data_object check (jsonb_typeof(parsed_data) = 'object'),
    constraint insurance_declaration_imports_warnings_array check (jsonb_typeof(parse_warnings) = 'array'),
    constraint insurance_declaration_imports_status_valid check (status in ('pending_confirmation', 'confirmed', 'cancelled', 'failed'))
);

create index insurance_declaration_imports_policy_id_idx
on public.insurance_declaration_imports (policy_id, created_at desc);

create index insurance_declaration_imports_company_id_idx
on public.insurance_declaration_imports (company_id);

create unique index insurance_declaration_imports_active_file_unique
on public.insurance_declaration_imports (policy_id, file_sha256)
where status in ('pending_confirmation', 'confirmed');

create table public.insurance_declaration_sequences (
    year integer primary key,
    last_value integer not null,
    constraint insurance_declaration_sequences_year_valid check (year between 1900 and 2200),
    constraint insurance_declaration_sequences_value_valid check (last_value > 0)
);

create table public.insurance_declarations (
    id uuid primary key default gen_random_uuid(),
    declaration_number text not null unique,
    declaration_import_id uuid unique references public.insurance_declaration_imports(id) on delete restrict,
    policy_id uuid not null references public.insurance_policies(id) on delete restrict,
    company_id uuid not null references public.insurance_companies(id) on delete restrict,
    source_type text not null,
    source_file_name text,
    received_at timestamptz not null default now(),
    status text not null default 'pending_review',
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint insurance_declarations_number_valid check (declaration_number ~ '^DEC-[0-9]{4}-[0-9]{4,}$'),
    constraint insurance_declarations_source_valid check (source_type in ('manual_upload', 'email', 'api')),
    constraint insurance_declarations_status_valid check (status in ('draft', 'pending_review', 'confirmed', 'covered', 'completed', 'cancelled'))
);

alter table public.insurance_declaration_imports
add constraint insurance_declaration_imports_confirmed_declaration_fkey
foreign key (confirmed_declaration_id)
references public.insurance_declarations(id)
on delete restrict;

create index insurance_declarations_policy_id_idx
on public.insurance_declarations (policy_id, received_at desc);

create index insurance_declarations_company_id_idx
on public.insurance_declarations (company_id, received_at desc);

create index insurance_declarations_status_idx
on public.insurance_declarations (status, received_at desc);

create table public.insurance_shipments (
    id uuid primary key default gen_random_uuid(),
    declaration_id uuid not null references public.insurance_declarations(id) on delete cascade,
    vessel_name text,
    imo_number text,
    voyage_number text,
    flag text,
    built_year integer,
    cargo_name text,
    cargo_description text,
    cargo_marks text,
    quantity numeric(20, 4),
    quantity_unit text,
    quantity_tolerance_percent numeric(8, 4),
    invoice_number text,
    contract_number text,
    bill_of_lading_number text,
    invoice_value numeric(20, 2),
    insured_value numeric(20, 2),
    currency text,
    loading_port text,
    discharge_port text,
    via_port text,
    origin_country text,
    destination_country text,
    etd timestamptz,
    eta timestamptz,
    insurance_rate numeric(12, 8),
    premium numeric(20, 2),
    certificate_number text,
    coverage_status text,
    extra_data jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint insurance_shipments_imo_valid check (imo_number is null or imo_number ~ '^[0-9]{7}$'),
    constraint insurance_shipments_built_year_valid check (built_year is null or built_year between 1800 and 2200),
    constraint insurance_shipments_quantity_nonnegative check (quantity is null or quantity >= 0),
    constraint insurance_shipments_quantity_tolerance_nonnegative check (quantity_tolerance_percent is null or quantity_tolerance_percent >= 0),
    constraint insurance_shipments_invoice_value_nonnegative check (invoice_value is null or invoice_value >= 0),
    constraint insurance_shipments_insured_value_nonnegative check (insured_value is null or insured_value >= 0),
    constraint insurance_shipments_rate_nonnegative check (insurance_rate is null or insurance_rate >= 0),
    constraint insurance_shipments_premium_nonnegative check (premium is null or premium >= 0),
    constraint insurance_shipments_currency_valid check (currency is null or currency ~ '^[A-Z]{3}$'),
    constraint insurance_shipments_dates_valid check (eta is null or etd is null or eta >= etd),
    constraint insurance_shipments_extra_data_object check (jsonb_typeof(extra_data) = 'object')
);

create index insurance_shipments_declaration_id_idx
on public.insurance_shipments (declaration_id);

create index insurance_shipments_imo_number_idx
on public.insurance_shipments (imo_number)
where imo_number is not null;

create index insurance_shipments_vessel_name_idx
on public.insurance_shipments (lower(vessel_name))
where vessel_name is not null;

create index insurance_shipments_voyage_dates_idx
on public.insurance_shipments (etd, eta);

create index insurance_shipments_certificate_number_idx
on public.insurance_shipments (certificate_number)
where certificate_number is not null;

create table public.insurance_documents (
    id uuid primary key default gen_random_uuid(),
    policy_id uuid references public.insurance_policies(id) on delete cascade,
    declaration_id uuid references public.insurance_declarations(id) on delete cascade,
    shipment_id uuid references public.insurance_shipments(id) on delete cascade,
    document_type text not null,
    file_name text not null,
    content_type text,
    file_size bigint,
    storage_bucket text not null,
    storage_path text not null,
    file_sha256 text,
    uploaded_at timestamptz not null default now(),
    constraint insurance_documents_owner_required check (
        policy_id is not null or declaration_id is not null or shipment_id is not null
    ),
    constraint insurance_documents_type_valid check (
        document_type in (
            'framework_policy',
            'declaration_form',
            'certificate',
            'endorsement',
            'invoice',
            'bill_of_lading',
            'other'
        )
    ),
    constraint insurance_documents_size_valid check (file_size is null or file_size >= 0),
    constraint insurance_documents_hash_valid check (file_sha256 is null or file_sha256 ~ '^[0-9a-f]{64}$'),
    constraint insurance_documents_storage_unique unique (storage_bucket, storage_path)
);

create index insurance_documents_policy_id_idx
on public.insurance_documents (policy_id, uploaded_at desc)
where policy_id is not null;

create index insurance_documents_declaration_id_idx
on public.insurance_documents (declaration_id, uploaded_at desc)
where declaration_id is not null;

create index insurance_documents_shipment_id_idx
on public.insurance_documents (shipment_id, uploaded_at desc)
where shipment_id is not null;

create or replace function public.set_insurance_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create trigger insurance_companies_set_updated_at
before update on public.insurance_companies
for each row execute function public.set_insurance_updated_at();

create trigger insurance_policies_set_updated_at
before update on public.insurance_policies
for each row execute function public.set_insurance_updated_at();

create trigger insurance_declaration_imports_set_updated_at
before update on public.insurance_declaration_imports
for each row execute function public.set_insurance_updated_at();

create trigger insurance_declarations_set_updated_at
before update on public.insurance_declarations
for each row execute function public.set_insurance_updated_at();

create trigger insurance_shipments_set_updated_at
before update on public.insurance_shipments
for each row execute function public.set_insurance_updated_at();

create or replace view public.insurance_policy_summaries
with (security_invoker = true)
as
select
    p.id,
    p.company_id,
    c.name as company_name,
    p.policy_name,
    p.policy_number,
    p.insurer,
    p.start_date,
    p.end_date,
    p.currency,
    p.rate,
    p.shipment_limit,
    p.annual_estimated_value,
    p.valuation_basis,
    p.deductible,
    p.cargo_scope,
    p.territory,
    p.transport_mode,
    p.insurance_clause,
    p.war_risk,
    p.special_conditions,
    case
        when p.status = 'cancelled' then 'cancelled'
        when current_date < p.start_date then 'pending'
        when current_date > p.end_date then 'expired'
        when p.end_date - current_date <= 30 then 'expiring_soon'
        else 'active'
    end as status,
    coalesce(declaration_stats.declaration_count, 0)::integer as declaration_count,
    coalesce(shipment_stats.insured_value_total, 0)::numeric(20, 2) as insured_value_total,
    coalesce(shipment_stats.premium_total, 0)::numeric(20, 2) as premium_total,
    coalesce(shipment_stats.active_shipment_count, 0)::integer as active_shipment_count,
    coalesce(declaration_stats.pending_declaration_count, 0)::integer as pending_declaration_count,
    recent.declaration_number as recent_declaration_number,
    recent.vessel_name as recent_vessel_name,
    recent.cargo_name as recent_cargo_name,
    recent.received_at as recent_declaration_at,
    coalesce(search_data.search_text, '') as search_text,
    p.created_at,
    p.updated_at
from public.insurance_policies p
join public.insurance_companies c on c.id = p.company_id
left join lateral (
    select
        count(*) as declaration_count,
        count(*) filter (where d.status = 'pending_review') as pending_declaration_count
    from public.insurance_declarations d
    where d.policy_id = p.id
) declaration_stats on true
left join lateral (
    select
        sum(s.insured_value) as insured_value_total,
        sum(s.premium) as premium_total,
        count(*) filter (
            where s.etd <= now()
              and (s.eta is null or s.eta >= now())
        ) as active_shipment_count
    from public.insurance_shipments s
    join public.insurance_declarations d on d.id = s.declaration_id
    where d.policy_id = p.id
) shipment_stats on true
left join lateral (
    select
        d.declaration_number,
        d.received_at,
        s.vessel_name,
        s.cargo_name
    from public.insurance_declarations d
    left join public.insurance_shipments s on s.declaration_id = d.id
    where d.policy_id = p.id
    order by d.received_at desc, s.created_at
    limit 1
) recent on true
left join lateral (
    select string_agg(
        concat_ws(
            ' ',
            d.declaration_number,
            d.source_file_name,
            s.vessel_name,
            s.imo_number,
            s.cargo_name,
            s.certificate_number,
            s.loading_port,
            s.discharge_port
        ),
        ' '
    ) as search_text
    from public.insurance_declarations d
    left join public.insurance_shipments s on s.declaration_id = d.id
    where d.policy_id = p.id
) search_data on true;

create or replace view public.insurance_dashboard_summary
with (security_invoker = true)
as
select
    (
        select count(*)
        from public.insurance_policies p
        where p.status <> 'cancelled'
          and current_date between p.start_date and p.end_date
    )::integer as active_policy_count,
    (
        select count(*)
        from public.insurance_declarations d
        where extract(year from d.received_at) = extract(year from current_date)
    )::integer as current_year_declaration_count,
    coalesce((select sum(s.insured_value) from public.insurance_shipments s), 0)::numeric(20, 2) as insured_value_total,
    (
        select count(*)
        from public.insurance_shipments s
        where s.etd <= now()
          and (s.eta is null or s.eta >= now())
    )::integer as active_shipment_count,
    (
        select count(*)
        from public.insurance_declarations d
        where d.status = 'pending_review'
    )::integer as pending_declaration_count;

create or replace function public.confirm_insurance_declaration_import(
    p_import_id uuid,
    p_status text default 'pending_review',
    p_notes text default null,
    p_received_at timestamptz default null,
    p_shipments jsonb default null
)
returns table (
    declaration_id uuid,
    declaration_number text
)
language plpgsql
set search_path = public
as $$
declare
    v_import public.insurance_declaration_imports%rowtype;
    v_policy_company_id uuid;
    v_shipments jsonb;
    v_shipment jsonb;
    v_sequence integer;
    v_year integer;
    v_declaration_id uuid;
    v_declaration_number text;
begin
    if p_status not in ('draft', 'pending_review', 'confirmed', 'covered', 'completed', 'cancelled') then
        raise exception 'invalid declaration status: %', p_status using errcode = '22023';
    end if;

    select *
    into v_import
    from public.insurance_declaration_imports
    where id = p_import_id
    for update;

    if not found then
        raise exception 'declaration import not found' using errcode = 'P0002';
    end if;
    if v_import.status <> 'pending_confirmation' then
        raise exception 'declaration import is already processed' using errcode = '23505';
    end if;

    select company_id
    into v_policy_company_id
    from public.insurance_policies
    where id = v_import.policy_id;

    if v_policy_company_id is null or v_policy_company_id <> v_import.company_id then
        raise exception 'declaration import policy/company mismatch' using errcode = '23503';
    end if;

    v_shipments := coalesce(p_shipments, v_import.parsed_data -> 'shipments');
    if v_shipments is null or jsonb_typeof(v_shipments) <> 'array' or jsonb_array_length(v_shipments) = 0 then
        raise exception 'at least one shipment is required' using errcode = '22023';
    end if;

    v_year := extract(
        year from coalesce(
            p_received_at,
            nullif(v_import.parsed_data ->> 'received_at', '')::timestamptz,
            now()
        )
    )::integer;

    insert into public.insurance_declaration_sequences (year, last_value)
    values (v_year, 1)
    on conflict (year)
    do update set last_value = public.insurance_declaration_sequences.last_value + 1
    returning last_value into v_sequence;

    v_declaration_number := 'DEC-' || v_year::text || '-' || lpad(v_sequence::text, 4, '0');

    insert into public.insurance_declarations (
        declaration_number,
        declaration_import_id,
        policy_id,
        company_id,
        source_type,
        source_file_name,
        received_at,
        status,
        notes
    )
    values (
        v_declaration_number,
        v_import.id,
        v_import.policy_id,
        v_import.company_id,
        v_import.source_type,
        v_import.source_file_name,
        coalesce(p_received_at, nullif(v_import.parsed_data ->> 'received_at', '')::timestamptz, now()),
        p_status,
        p_notes
    )
    returning id into v_declaration_id;

    for v_shipment in select value from jsonb_array_elements(v_shipments)
    loop
        insert into public.insurance_shipments (
            declaration_id,
            vessel_name,
            imo_number,
            voyage_number,
            flag,
            built_year,
            cargo_name,
            cargo_description,
            cargo_marks,
            quantity,
            quantity_unit,
            quantity_tolerance_percent,
            invoice_number,
            contract_number,
            bill_of_lading_number,
            invoice_value,
            insured_value,
            currency,
            loading_port,
            discharge_port,
            via_port,
            origin_country,
            destination_country,
            etd,
            eta,
            insurance_rate,
            premium,
            certificate_number,
            coverage_status,
            extra_data
        )
        values (
            v_declaration_id,
            nullif(v_shipment ->> 'vessel_name', ''),
            nullif(v_shipment ->> 'imo_number', ''),
            nullif(v_shipment ->> 'voyage_number', ''),
            nullif(v_shipment ->> 'flag', ''),
            nullif(v_shipment ->> 'built_year', '')::integer,
            nullif(v_shipment ->> 'cargo_name', ''),
            nullif(v_shipment ->> 'cargo_description', ''),
            nullif(v_shipment ->> 'cargo_marks', ''),
            nullif(v_shipment ->> 'quantity', '')::numeric,
            nullif(v_shipment ->> 'quantity_unit', ''),
            nullif(v_shipment ->> 'quantity_tolerance_percent', '')::numeric,
            nullif(v_shipment ->> 'invoice_number', ''),
            nullif(v_shipment ->> 'contract_number', ''),
            nullif(v_shipment ->> 'bill_of_lading_number', ''),
            nullif(v_shipment ->> 'invoice_value', '')::numeric,
            nullif(v_shipment ->> 'insured_value', '')::numeric,
            nullif(v_shipment ->> 'currency', ''),
            nullif(v_shipment ->> 'loading_port', ''),
            nullif(v_shipment ->> 'discharge_port', ''),
            nullif(v_shipment ->> 'via_port', ''),
            nullif(v_shipment ->> 'origin_country', ''),
            nullif(v_shipment ->> 'destination_country', ''),
            nullif(v_shipment ->> 'etd', '')::timestamptz,
            nullif(v_shipment ->> 'eta', '')::timestamptz,
            nullif(v_shipment ->> 'insurance_rate', '')::numeric,
            nullif(v_shipment ->> 'premium', '')::numeric,
            nullif(v_shipment ->> 'certificate_number', ''),
            nullif(v_shipment ->> 'coverage_status', ''),
            coalesce(v_shipment -> 'extra_data', '{}'::jsonb)
        );
    end loop;

    insert into public.insurance_documents (
        policy_id,
        declaration_id,
        document_type,
        file_name,
        content_type,
        file_size,
        storage_bucket,
        storage_path,
        file_sha256
    )
    values (
        v_import.policy_id,
        v_declaration_id,
        'declaration_form',
        v_import.source_file_name,
        v_import.content_type,
        v_import.file_size,
        v_import.storage_bucket,
        v_import.storage_path,
        v_import.file_sha256
    );

    update public.insurance_declaration_imports
    set status = 'confirmed',
        confirmed_declaration_id = v_declaration_id
    where id = v_import.id;

    declaration_id := v_declaration_id;
    declaration_number := v_declaration_number;
    return next;
end;
$$;

alter table public.insurance_companies enable row level security;
alter table public.insurance_policies enable row level security;
alter table public.insurance_declaration_imports enable row level security;
alter table public.insurance_declaration_sequences enable row level security;
alter table public.insurance_declarations enable row level security;
alter table public.insurance_shipments enable row level security;
alter table public.insurance_documents enable row level security;

revoke all on table public.insurance_companies from public, anon, authenticated;
revoke all on table public.insurance_policies from public, anon, authenticated;
revoke all on table public.insurance_declaration_imports from public, anon, authenticated;
revoke all on table public.insurance_declaration_sequences from public, anon, authenticated;
revoke all on table public.insurance_declarations from public, anon, authenticated;
revoke all on table public.insurance_shipments from public, anon, authenticated;
revoke all on table public.insurance_documents from public, anon, authenticated;
revoke all on table public.insurance_policy_summaries from public, anon, authenticated;
revoke all on table public.insurance_dashboard_summary from public, anon, authenticated;
revoke execute on function public.set_insurance_updated_at() from public, anon, authenticated;
revoke execute on function public.confirm_insurance_declaration_import(uuid, text, text, timestamptz, jsonb) from public, anon, authenticated;

grant select, insert, update, delete on table public.insurance_companies to service_role;
grant select, insert, update, delete on table public.insurance_policies to service_role;
grant select, insert, update, delete on table public.insurance_declaration_imports to service_role;
grant select, insert, update on table public.insurance_declaration_sequences to service_role;
grant select, insert, update, delete on table public.insurance_declarations to service_role;
grant select, insert, update, delete on table public.insurance_shipments to service_role;
grant select, insert, update, delete on table public.insurance_documents to service_role;
grant select on table public.insurance_policy_summaries to service_role;
grant select on table public.insurance_dashboard_summary to service_role;
grant execute on function public.confirm_insurance_declaration_import(uuid, text, text, timestamptz, jsonb) to service_role;

comment on table public.insurance_policies is 'Framework/open-cover marine cargo insurance policies.';
comment on table public.insurance_declaration_imports is 'Uploaded declaration files awaiting human confirmation.';
comment on table public.insurance_declarations is 'Confirmed or in-progress declarations under a framework policy.';
comment on table public.insurance_shipments is 'Shipment risk objects extracted from declarations.';
comment on table public.insurance_documents is 'Private storage metadata for policy, declaration, shipment, and certificate files.';

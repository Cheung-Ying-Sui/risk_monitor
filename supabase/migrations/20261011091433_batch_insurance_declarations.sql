-- One row in the voyage worksheet is one declaration, even when IMO repeats.
-- The source import remains a single archived bundle; all inserts commit together.
alter table public.insurance_documents
drop constraint insurance_documents_storage_unique;

create unique index insurance_documents_non_declaration_storage_unique
on public.insurance_documents (storage_bucket, storage_path)
where declaration_id is null;

create unique index insurance_documents_declaration_storage_unique
on public.insurance_documents (storage_bucket, storage_path, declaration_id)
where declaration_id is not null;

create function public.confirm_insurance_declaration_import_batch(
    p_import_id uuid,
    p_notes text default null,
    p_received_at timestamptz default null,
    p_shipments jsonb default null
)
returns table (declaration_id uuid, declaration_number text)
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_import public.insurance_declaration_imports%rowtype;
    v_shipment jsonb;
    v_year integer;
    v_sequence integer;
    v_id uuid;
    v_number text;
    v_first_id uuid;
    v_count integer := 0;
begin
    select * into v_import from public.insurance_declaration_imports
    where id = p_import_id for update;
    if not found then
        raise exception 'declaration import not found' using errcode = 'P0002';
    end if;
    if v_import.status <> 'pending_confirmation' then
        raise exception 'declaration import is already processed' using errcode = '23505';
    end if;
    if not exists (
        select 1 from public.insurance_policies
        where id = v_import.policy_id and company_id = v_import.company_id and status <> 'cancelled'
    ) then
        raise exception 'declaration import policy/company mismatch' using errcode = '23503';
    end if;
    if p_shipments is null then p_shipments := v_import.parsed_data -> 'shipments'; end if;
    if p_shipments is null or jsonb_typeof(p_shipments) <> 'array' or jsonb_array_length(p_shipments) = 0 then
        raise exception 'at least one shipment is required' using errcode = '22023';
    end if;
    if jsonb_array_length(p_shipments) > 500 then
        raise exception 'batch exceeds 500 rows' using errcode = '22023';
    end if;
    v_year := extract(year from coalesce(p_received_at,
        nullif(v_import.parsed_data ->> 'received_at', '')::timestamptz, now()))::integer;
    for v_shipment in select value from jsonb_array_elements(p_shipments)
    loop
        if jsonb_typeof(v_shipment) <> 'object' then
            raise exception 'invalid shipment row' using errcode = '22023';
        end if;
        insert into public.insurance_declaration_sequences (year, last_value)
        values (v_year, 1)
        on conflict (year) do update
        set last_value = public.insurance_declaration_sequences.last_value + 1
        returning last_value into v_sequence;
        v_number := 'DEC-' || v_year::text || '-' || lpad(v_sequence::text, 4, '0');
        insert into public.insurance_declarations (
            declaration_number, declaration_import_id, policy_id, company_id,
            source_type, source_file_name, received_at, status, notes
        ) values (
            v_number, case when v_count = 0 then v_import.id else null end,
            v_import.policy_id, v_import.company_id, v_import.source_type,
            v_import.source_file_name,
            coalesce(p_received_at, nullif(v_import.parsed_data ->> 'received_at', '')::timestamptz, now()),
            'pending_review', p_notes
        ) returning id into v_id;
        if v_first_id is null then v_first_id := v_id; end if;
        insert into public.insurance_shipments (
            declaration_id, vessel_name, imo_number, voyage_number, flag, built_year,
            cargo_name, cargo_description, cargo_marks, quantity, quantity_unit,
            quantity_tolerance_percent, invoice_number, contract_number,
            bill_of_lading_number, invoice_value, insured_value, currency,
            loading_port, discharge_port, via_port, origin_country,
            destination_country, etd, eta, insurance_rate, premium,
            certificate_number, coverage_status, extra_data
        ) values (
            v_id, nullif(v_shipment ->> 'vessel_name', ''),
            nullif(v_shipment ->> 'imo_number', ''), nullif(v_shipment ->> 'voyage_number', ''),
            nullif(v_shipment ->> 'flag', ''), nullif(v_shipment ->> 'built_year', '')::integer,
            nullif(v_shipment ->> 'cargo_name', ''), nullif(v_shipment ->> 'cargo_description', ''),
            nullif(v_shipment ->> 'cargo_marks', ''), nullif(v_shipment ->> 'quantity', '')::numeric,
            nullif(v_shipment ->> 'quantity_unit', ''), nullif(v_shipment ->> 'quantity_tolerance_percent', '')::numeric,
            nullif(v_shipment ->> 'invoice_number', ''), nullif(v_shipment ->> 'contract_number', ''),
            nullif(v_shipment ->> 'bill_of_lading_number', ''), nullif(v_shipment ->> 'invoice_value', '')::numeric,
            nullif(v_shipment ->> 'insured_value', '')::numeric, nullif(v_shipment ->> 'currency', ''),
            nullif(v_shipment ->> 'loading_port', ''), nullif(v_shipment ->> 'discharge_port', ''),
            nullif(v_shipment ->> 'via_port', ''), nullif(v_shipment ->> 'origin_country', ''),
            nullif(v_shipment ->> 'destination_country', ''), nullif(v_shipment ->> 'etd', '')::timestamptz,
            nullif(v_shipment ->> 'eta', '')::timestamptz, nullif(v_shipment ->> 'insurance_rate', '')::numeric,
            nullif(v_shipment ->> 'premium', '')::numeric, nullif(v_shipment ->> 'certificate_number', ''),
            nullif(v_shipment ->> 'coverage_status', ''), coalesce(v_shipment -> 'extra_data', '{}'::jsonb)
        );
        insert into public.insurance_documents (
            policy_id, declaration_id, document_type, file_name, content_type,
            file_size, storage_bucket, storage_path, file_sha256
        ) values (
            v_import.policy_id, v_id, 'declaration_form', v_import.source_file_name,
            v_import.content_type, v_import.file_size, v_import.storage_bucket,
            v_import.storage_path, v_import.file_sha256
        );
        declaration_id := v_id;
        declaration_number := v_number;
        return next;
        v_count := v_count + 1;
    end loop;
    update public.insurance_declaration_imports
    set status = 'confirmed', confirmed_declaration_id = v_first_id
    where id = v_import.id;
end;
$$;

revoke execute on function public.confirm_insurance_declaration_import_batch(uuid, text, timestamptz, jsonb)
from public, anon, authenticated;
grant execute on function public.confirm_insurance_declaration_import_batch(uuid, text, timestamptz, jsonb)
to service_role;

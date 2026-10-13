-- Submission creates a screening queue item; it is not a sanctions clearance.
create or replace function public.submit_insurance_draft(
    p_declaration_id uuid,
    p_screening jsonb
)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_status text;
    v_extra jsonb;
begin
    select status into v_status from public.insurance_declarations
    where id = p_declaration_id for update;
    if not found then
        raise exception 'declaration not found' using errcode = 'P0002';
    end if;
    if v_status <> 'draft' then
        raise exception 'declaration is not a draft' using errcode = '23505';
    end if;
    if (select count(*) from public.insurance_shipments where declaration_id = p_declaration_id) <> 1 then
        raise exception 'draft requires one shipment' using errcode = '22023';
    end if;
    select extra_data into v_extra from public.insurance_shipments
    where declaration_id = p_declaration_id for update;
    if not (
        nullif(btrim(v_extra ->> 'insured_name'), '') is not null or
        nullif(btrim(v_extra ->> 'shipper'), '') is not null or
        nullif(btrim(v_extra ->> 'consignee'), '') is not null or
        nullif(btrim(v_extra ->> 'cedant'), '') is not null
    ) then
        raise exception 'at least one screening party is required' using errcode = '22023';
    end if;
    update public.insurance_shipments
    set extra_data = (extra_data - 'sanctions_workflow') || jsonb_build_object(
        'sanctions_screening', jsonb_build_object(
            'status', 'pending', 'source', 'OFAC SDN',
            'possible_match_count', 0, 'parties', '[]'::jsonb
        )
    ) where declaration_id = p_declaration_id;
    update public.insurance_declarations
    set status = 'pending_review' where id = p_declaration_id;
    return true;
end;
$$;

revoke execute on function public.submit_insurance_draft(uuid, jsonb)
from public, anon, authenticated;
grant execute on function public.submit_insurance_draft(uuid, jsonb)
to service_role;

-- The report and every subject's OFAC evidence must be present when coverage is confirmed.
create or replace function public.confirm_insurance_underwriting(
    p_declaration_id uuid,
    p_rate numeric
)
returns table (shipment_id uuid, premium numeric)
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_declaration public.insurance_declarations%rowtype;
    v_shipment public.insurance_shipments%rowtype;
    v_workflow jsonb;
    v_report jsonb;
    v_party jsonb;
    v_name text;
    v_role text;
    v_party_count integer := 0;
begin
    if p_rate is null or p_rate < 0 or p_rate > 100 then
        raise exception 'rate must be between 0 and 100 percent' using errcode = '22023';
    end if;
    select * into v_declaration from public.insurance_declarations
    where id = p_declaration_id for update;
    if not found then
        raise exception 'declaration not found' using errcode = 'P0002';
    end if;
    if v_declaration.status <> 'pending_review' then
        raise exception 'declaration is not pending underwriting' using errcode = '23505';
    end if;
    if (select count(*) from public.insurance_shipments where declaration_id = p_declaration_id) <> 1 then
        raise exception 'underwriting confirmation requires one shipment per declaration' using errcode = '22023';
    end if;
    select * into v_shipment from public.insurance_shipments
    where declaration_id = p_declaration_id for update;
    if v_shipment.insured_value is null or v_shipment.currency is null then
        raise exception 'insured value and currency are required' using errcode = '22023';
    end if;

    v_workflow := v_shipment.extra_data -> 'sanctions_workflow';
    v_report := v_workflow -> 'report';
    if v_report is null or nullif(v_report ->> 'case_fingerprint', '') is null
       or nullif(v_report ->> 'generated_at', '') is null
       or (v_shipment.extra_data #>> '{sanctions_screening,status}') is distinct from 'completed' then
        raise exception 'sanctions screening report is required before underwriting' using errcode = '22023';
    end if;
    if not exists (
        select 1 from public.insurance_documents d
        where d.id::text = v_report ->> 'document_id'
          and d.declaration_id = p_declaration_id
          and d.content_type like 'text/html%'
          and d.file_sha256 = v_report ->> 'sha256'
    ) then
        raise exception 'sanctions screening report document is missing' using errcode = '22023';
    end if;

    foreach v_role in array array['insured_name', 'shipper', 'consignee', 'cedant'] loop
        v_name := nullif(btrim(v_shipment.extra_data ->> v_role), '');
        if v_name is null then
            continue;
        end if;
        v_party_count := v_party_count + 1;
        v_party := v_workflow -> 'parties' -> v_role;
        if v_party is null or (v_party ->> 'name') is distinct from v_name
           or (v_party #>> '{preliminary,query}') is distinct from v_name
           or nullif(v_party #>> '{preliminary,screened_at}', '') is null
           or nullif(v_party #>> '{evidence,document_id}', '') is null
           or nullif(v_party #>> '{review,reviewer}', '') is null
           or nullif(v_party #>> '{review,reviewed_at}', '') is null then
            raise exception 'sanctions screening is incomplete for %', v_role using errcode = '22023';
        end if;
        if (v_party #>> '{review,result}') is distinct from 'no_match' then
            raise exception 'sanctions match requires compliance escalation for %', v_role using errcode = '22023';
        end if;
        if (v_party #>> '{review,reviewed_at}')::timestamptz > (v_report ->> 'generated_at')::timestamptz then
            raise exception 'sanctions screening report is stale for %', v_role using errcode = '22023';
        end if;
        if not exists (
            select 1 from public.insurance_documents d
            where d.id::text = (v_party #>> '{evidence,document_id}')
              and d.declaration_id = p_declaration_id
              and d.shipment_id = v_shipment.id
              and d.content_type in ('image/png', 'image/jpeg', 'image/webp')
              and d.file_sha256 = v_party #>> '{evidence,sha256}'
        ) then
            raise exception 'OFAC screenshot is missing for %', v_role using errcode = '22023';
        end if;
    end loop;
    if v_party_count = 0 then
        raise exception 'at least one screening party is required' using errcode = '22023';
    end if;

    update public.insurance_shipments
    set insurance_rate = p_rate,
        premium = round(v_shipment.insured_value * p_rate / 100, 2)
    where id = v_shipment.id;
    update public.insurance_declarations set status = 'confirmed'
    where id = p_declaration_id;
    shipment_id := v_shipment.id;
    premium := round(v_shipment.insured_value * p_rate / 100, 2);
    return next;
end;
$$;

revoke execute on function public.confirm_insurance_underwriting(uuid, numeric)
from public, anon, authenticated;
grant execute on function public.confirm_insurance_underwriting(uuid, numeric)
to service_role;

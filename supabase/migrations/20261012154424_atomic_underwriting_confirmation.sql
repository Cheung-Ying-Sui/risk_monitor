-- Server verifies Storage bytes before calling this service-role-only RPC.
-- Row locks bind that receipt to the same report and screening snapshot; network
-- I/O is deliberately outside the database transaction.
create or replace function public.confirm_insurance_underwriting_atomic(
    p_declaration_id uuid, p_rate numeric, p_expected_workflow jsonb,
    p_verified_sha256 text, p_expected_insured_value numeric, p_expected_currency text
)
returns table (shipment_id uuid, premium numeric, applied boolean)
language plpgsql security invoker set search_path = '' as $$
declare
    v_declaration public.insurance_declarations%rowtype;
    v_shipment public.insurance_shipments%rowtype;
    v_workflow jsonb;
    v_report jsonb;
    v_terms jsonb;
begin
    if p_rate is null or p_rate::text in ('NaN', 'Infinity', '-Infinity') or p_rate < 0 or p_rate > 100 then
        raise exception 'invalid rate' using errcode = '22023';
    end if;
    select * into v_declaration from public.insurance_declarations where id = p_declaration_id for update;
    if not found then raise exception 'declaration not found' using errcode = 'P0002'; end if;
    if (select count(*) from public.insurance_shipments where declaration_id = p_declaration_id) <> 1 then
        raise exception 'confirmation requires exactly one shipment' using errcode = '22023';
    end if;
    select * into v_shipment from public.insurance_shipments where declaration_id = p_declaration_id for update;
    v_workflow := v_shipment.extra_data -> 'sanctions_workflow';
    v_report := v_workflow -> 'report';
    v_terms := v_shipment.extra_data -> 'underwriting_terms';
    if v_workflow is distinct from p_expected_workflow
       or v_shipment.insured_value is distinct from p_expected_insured_value
       or v_shipment.currency is distinct from p_expected_currency then
        raise exception 'screening or insured value changed' using errcode = '40001';
    end if;
    if v_shipment.insured_value is null or v_shipment.insured_value < 0
       or v_shipment.insured_value::text in ('NaN', 'Infinity', '-Infinity')
       or nullif(btrim(v_shipment.currency), '') is null
       or v_report is null or nullif(v_report ->> 'downloaded_at', '') is null
       or nullif(v_report ->> 'case_fingerprint', '') is null
       or nullif(p_verified_sha256, '') is null
       or (v_report ->> 'sha256') is distinct from p_verified_sha256
       or (v_report #> array['screening_snapshot', v_shipment.id::text]) is distinct from (v_workflow -> 'parties') then
        raise exception 'valid downloaded report and screening snapshot required' using errcode = '22023';
    end if;
    -- Lock report and screenshot metadata against concurrent edits/deletions.
    perform 1 from public.insurance_documents d where d.declaration_id = p_declaration_id for share;
    if not exists (select 1 from public.insurance_documents d where d.id::text = v_report ->> 'document_id'
        and d.declaration_id = p_declaration_id and d.file_sha256 = p_verified_sha256
        and d.content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') then
        raise exception 'verified report document required' using errcode = '22023';
    end if;
    if v_declaration.status = 'confirmed' then
        if (v_terms ->> 'rate')::numeric is distinct from p_rate
           or v_terms ->> 'status' is distinct from 'confirmed'
           or v_terms ->> 'report_sha256' is distinct from p_verified_sha256 then
            raise exception 'already confirmed with different terms' using errcode = '23505';
        end if;
        return query select v_shipment.id, v_shipment.premium, false;
        return;
    end if;
    if v_declaration.status <> 'pending_review' then
        raise exception 'declaration is not pending underwriting' using errcode = '23505';
    end if;
    -- Reuse existing guards and calculation. Both writes roll back together.
    perform * from public.confirm_insurance_underwriting_terms(p_declaration_id, p_rate);
    perform * from public.confirm_insurance_underwriting(p_declaration_id);
    return query select v_shipment.id, round(v_shipment.insured_value * p_rate / 100, 2), true;
end;
$$;
revoke execute on function public.confirm_insurance_underwriting_atomic(uuid,numeric,jsonb,text,numeric,text)
from public, anon, authenticated;
grant execute on function public.confirm_insurance_underwriting_atomic(uuid,numeric,jsonb,text,numeric,text) to service_role;

-- In-flight screening requests must not invalidate a just-confirmed declaration.
create or replace function public.guard_confirmed_insurance_screening()
returns trigger language plpgsql security invoker set search_path = '' as $$
begin
    if (new.extra_data -> 'sanctions_workflow') is distinct from (old.extra_data -> 'sanctions_workflow')
       and exists (select 1 from public.insurance_declarations d
                   where d.id = old.declaration_id and d.status in ('confirmed', 'covered', 'completed')) then
        raise exception 'confirmed screening cannot be changed' using errcode = '23505';
    end if;
    return new;
end;
$$;
revoke execute on function public.guard_confirmed_insurance_screening() from public, anon, authenticated;
create trigger guard_confirmed_insurance_screening before update on public.insurance_shipments
for each row execute function public.guard_confirmed_insurance_screening();

-- Preserve the existing full OFAC evidence guard in the two-argument function,
-- but remove direct application access to its one-step confirmation path.
revoke execute on function public.confirm_insurance_underwriting(uuid, numeric)
from public, anon, authenticated, service_role;

create or replace function public.confirm_insurance_underwriting_terms(
    p_declaration_id uuid, p_rate numeric
)
returns table (shipment_id uuid, premium numeric)
language plpgsql security invoker set search_path = '' as $$
declare
    v_shipment public.insurance_shipments%rowtype;
    v_report jsonb;
    v_premium numeric;
begin
    if p_rate is null or p_rate < 0 or p_rate > 100 then
        raise exception 'rate must be between 0 and 100 percent' using errcode = '22023';
    end if;
    perform 1 from public.insurance_declarations
    where id = p_declaration_id and status = 'pending_review' for update;
    if not found then
        raise exception 'declaration is not pending underwriting' using errcode = '23505';
    end if;
    if (select count(*) from public.insurance_shipments where declaration_id = p_declaration_id) <> 1 then
        raise exception 'underwriting terms require one shipment' using errcode = '22023';
    end if;
    select * into v_shipment from public.insurance_shipments
    where declaration_id = p_declaration_id for update;
    v_report := v_shipment.extra_data #> '{sanctions_workflow,report}';
    if v_shipment.insured_value is null or v_shipment.currency is null
       or nullif(v_report ->> 'sha256', '') is null
       or nullif(v_report ->> 'downloaded_at', '') is null
       or (v_shipment.extra_data #>> '{sanctions_screening,status}') is distinct from 'completed'
       or not exists (
          select 1 from public.insurance_documents d
          where d.id::text = v_report ->> 'document_id'
            and d.declaration_id = p_declaration_id
            and d.file_sha256 = v_report ->> 'sha256'
            and d.content_type like 'text/html%'
       ) then
        raise exception 'sanctions screening report and insured value are required before terms confirmation' using errcode = '22023';
    end if;
    v_premium := round(v_shipment.insured_value * p_rate / 100, 2);
    update public.insurance_shipments set extra_data = extra_data || jsonb_build_object(
        'underwriting_terms', jsonb_build_object(
            'status', 'confirmed', 'rate', p_rate, 'premium', v_premium,
            'insured_value', v_shipment.insured_value, 'currency', v_shipment.currency,
            'report_sha256', v_report ->> 'sha256',
            'confirmed_at', now()
        )
    ) where id = v_shipment.id;
    shipment_id := v_shipment.id;
    premium := v_premium;
    return next;
end;
$$;

revoke execute on function public.confirm_insurance_underwriting_terms(uuid, numeric)
from public, anon, authenticated;
grant execute on function public.confirm_insurance_underwriting_terms(uuid, numeric)
to service_role;

-- Final confirmation rechecks saved terms and then delegates to the existing
-- evidence-validation function. Only the no-rate function is exposed to the API.
create or replace function public.confirm_insurance_underwriting(p_declaration_id uuid)
returns table (shipment_id uuid, premium numeric)
language plpgsql security definer set search_path = '' as $$
declare
    v_shipment public.insurance_shipments%rowtype;
    v_terms jsonb;
begin
    perform 1 from public.insurance_declarations
    where id = p_declaration_id and status = 'pending_review' for update;
    if not found then
        raise exception 'declaration is not pending underwriting' using errcode = '23505';
    end if;
    if (select count(*) from public.insurance_shipments where declaration_id = p_declaration_id) <> 1 then
        raise exception 'final confirmation requires one shipment' using errcode = '22023';
    end if;
    select * into v_shipment from public.insurance_shipments
    where declaration_id = p_declaration_id for update;
    v_terms := v_shipment.extra_data -> 'underwriting_terms';
    if v_terms is null or v_terms ->> 'status' is distinct from 'confirmed'
       or (v_terms ->> 'report_sha256') is distinct from
          (v_shipment.extra_data #>> '{sanctions_workflow,report,sha256}')
       or (v_terms ->> 'insured_value')::numeric is distinct from v_shipment.insured_value
       or (v_terms ->> 'currency') is distinct from v_shipment.currency
       or (v_terms ->> 'premium')::numeric is distinct from
          round(v_shipment.insured_value * (v_terms ->> 'rate')::numeric / 100, 2) then
        raise exception 'confirmed underwriting terms are required' using errcode = '22023';
    end if;
    return query select result.shipment_id, result.premium
    from public.confirm_insurance_underwriting(p_declaration_id, (v_terms ->> 'rate')::numeric) result;
end;
$$;

revoke execute on function public.confirm_insurance_underwriting(uuid)
from public, anon, authenticated;
grant execute on function public.confirm_insurance_underwriting(uuid) to service_role;

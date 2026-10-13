create function public.confirm_insurance_underwriting(
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
    if v_shipment.extra_data #>> '{sanctions_screening,status}' <> 'completed' then
        raise exception 'sanctions screening has not completed' using errcode = '22023';
    end if;
    if coalesce((v_shipment.extra_data #>> '{sanctions_screening,possible_match_count}')::integer, 0) > 0 then
        raise exception 'possible sanctions match requires manual compliance review' using errcode = '22023';
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

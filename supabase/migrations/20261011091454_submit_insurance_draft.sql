create function public.submit_insurance_draft(
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
    if jsonb_typeof(p_screening) <> 'object' or p_screening ->> 'status' <> 'completed' then
        raise exception 'sanctions screening has not completed' using errcode = '22023';
    end if;
    update public.insurance_shipments
    set extra_data = extra_data || jsonb_build_object('sanctions_screening', p_screening)
    where declaration_id = p_declaration_id;
    update public.insurance_declarations
    set status = 'pending_review'
    where id = p_declaration_id;
    return true;
end;
$$;

revoke execute on function public.submit_insurance_draft(uuid, jsonb)
from public, anon, authenticated;
grant execute on function public.submit_insurance_draft(uuid, jsonb)
to service_role;

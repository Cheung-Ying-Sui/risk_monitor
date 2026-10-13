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
        when p.status = 'pending' then 'pending'
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

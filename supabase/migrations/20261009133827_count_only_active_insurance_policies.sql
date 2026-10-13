create or replace view public.insurance_dashboard_summary
with (security_invoker = true)
as
select
    (
        select count(*)
        from public.insurance_policies p
        where p.status = 'active'
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

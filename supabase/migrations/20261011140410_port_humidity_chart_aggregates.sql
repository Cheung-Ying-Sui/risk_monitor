-- Read-only, service-role-only aggregation of the Phase 1 hourly observations.
-- Calendar buckets use the port's local (Asia/Shanghai) date, not UTC dates.
create or replace function public.port_humidity_chart_aggregates(
    p_location_id uuid,
    p_source_id uuid,
    p_grid_latitude double precision,
    p_grid_longitude double precision,
    p_month integer,
    p_threshold double precision
)
returns table (bucket_type text, bucket_index integer, valid_hours bigint, exceedance_hours bigint)
language sql stable security invoker
set search_path = ''
as $$
    with valid_rows as (
        select
            extract(month from observed_at_utc at time zone 'Asia/Shanghai')::integer as local_month,
            extract(day from observed_at_utc at time zone 'Asia/Shanghai')::integer as local_day,
            relative_humidity_pct as rh
        from public.port_weather_hourly
        where weather_location_id = p_location_id
          and source_id = p_source_id
          and grid_latitude = p_grid_latitude
          and grid_longitude = p_grid_longitude
          and observed_at_utc >= '2015-12-31 16:00:00+00'::timestamptz
          and observed_at_utc < '2025-12-31 16:00:00+00'::timestamptz
          and relative_humidity_pct between 0 and 100
    )
    select 'month'::text, local_month, count(*)::bigint,
           count(*) filter (where rh >= p_threshold)::bigint
    from valid_rows
    group by local_month
    union all
    select 'day'::text, local_day, count(*)::bigint,
           count(*) filter (where rh >= p_threshold)::bigint
    from valid_rows
    where local_month = p_month
    group by local_day;
$$;

revoke all on function public.port_humidity_chart_aggregates(uuid, uuid, double precision, double precision, integer, double precision)
    from public, anon, authenticated;
grant execute on function public.port_humidity_chart_aggregates(uuid, uuid, double precision, double precision, integer, double precision)
    to service_role;

comment on function public.port_humidity_chart_aggregates(uuid, uuid, double precision, double precision, integer, double precision)
    is 'Counts valid ERA5 hourly RH readings and threshold exceedances by Shanghai calendar month and selected-month day, 2016–2025.';

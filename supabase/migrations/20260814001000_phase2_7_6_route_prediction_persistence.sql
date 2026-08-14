-- Phase 2.7.6: Route prediction persistence v1.
-- Purpose:
-- - Persist current-leg route prediction snapshots with time/version semantics.
-- - Preserve superseded route history for future prediction-error analysis.
-- - Enforce one active route prediction per MMSI.
-- - Provide atomic route activation through navigation.activate_route_prediction.

create schema if not exists navigation;

create table if not exists navigation.route_predictions (
    id uuid primary key default gen_random_uuid(),
    vessel_id uuid references core.vessels(id),
    mmsi text not null,
    origin_position_id bigint references tracking.vessel_positions(id),
    destination_raw text,
    destination_normalized text,
    destination_unlocode text,
    route_version integer not null,
    route_method text,
    route_geojson jsonb not null,
    great_circle_distance_nm double precision,
    navigable_distance_nm double precision,
    route_distance_ratio double precision,
    route_created_at timestamptz not null default now(),
    route_update_reason text not null,
    status text not null default 'active',
    superseded_at timestamptz,
    request_id text,
    created_at timestamptz not null default now(),
    constraint route_predictions_route_version_positive
        check (route_version > 0),
    constraint route_predictions_route_update_reason_valid
        check (
            route_update_reason in (
                'initial_route',
                'destination_changed',
                'route_deviation',
                'manual_refresh'
            )
        ),
    constraint route_predictions_status_valid
        check (status in ('active', 'superseded')),
    constraint route_predictions_route_geojson_object
        check (jsonb_typeof(route_geojson) = 'object'),
    constraint route_predictions_superseded_at_status_consistent
        check (
            (status = 'active' and superseded_at is null)
            or status = 'superseded'
        )
);

create unique index if not exists route_predictions_one_active_mmsi_unique
on navigation.route_predictions (mmsi)
where status = 'active';

create unique index if not exists route_predictions_mmsi_request_id_unique
on navigation.route_predictions (mmsi, request_id)
where request_id is not null;

create index if not exists idx_route_predictions_mmsi_version
on navigation.route_predictions (mmsi, route_version desc);

create index if not exists idx_route_predictions_mmsi_created_at
on navigation.route_predictions (mmsi, route_created_at desc);

comment on table navigation.route_predictions is
'Persisted current-leg route prediction snapshots. Superseded rows are retained for future route prediction error analysis.';

create or replace function navigation.activate_route_prediction(
    p_vessel_id uuid,
    p_mmsi text,
    p_origin_position_id bigint,
    p_destination_raw text,
    p_destination_normalized text,
    p_destination_unlocode text,
    p_route_method text,
    p_route_geojson jsonb,
    p_great_circle_distance_nm double precision,
    p_navigable_distance_nm double precision,
    p_route_distance_ratio double precision,
    p_route_update_reason text,
    p_request_id text default null
)
returns table (
    route_prediction_id uuid,
    route_version integer,
    old_route_prediction_id uuid,
    inserted boolean
)
language plpgsql
volatile
as $$
declare
    normalized_mmsi text;
    existing_id uuid;
    existing_version integer;
    previous_active_id uuid;
    next_version integer;
    new_id uuid;
begin
    normalized_mmsi := nullif(trim(p_mmsi), '');

    if normalized_mmsi is null then
        raise exception 'mmsi is required'
            using errcode = '22023';
    end if;

    if p_route_geojson is null or jsonb_typeof(p_route_geojson) <> 'object' then
        raise exception 'route_geojson must be a JSON object'
            using errcode = '22023';
    end if;

    if p_route_update_reason not in (
        'initial_route',
        'destination_changed',
        'route_deviation',
        'manual_refresh'
    ) then
        raise exception 'invalid route_update_reason: %', p_route_update_reason
            using errcode = '22023';
    end if;

    perform pg_advisory_xact_lock(hashtext('navigation.route_predictions:' || normalized_mmsi));

    if p_request_id is not null then
        select rp.id, rp.route_version
        into existing_id, existing_version
        from navigation.route_predictions rp
        where rp.mmsi = normalized_mmsi
          and rp.request_id = p_request_id
        limit 1;

        if existing_id is not null then
            route_prediction_id := existing_id;
            route_version := existing_version;
            old_route_prediction_id := null;
            inserted := false;
            return next;
            return;
        end if;
    end if;

    select rp.id
    into previous_active_id
    from navigation.route_predictions rp
    where rp.mmsi = normalized_mmsi
      and rp.status = 'active'
    for update;

    select coalesce(max(rp.route_version), 0) + 1
    into next_version
    from navigation.route_predictions rp
    where rp.mmsi = normalized_mmsi;

    if previous_active_id is not null then
        update navigation.route_predictions rp
        set status = 'superseded',
            superseded_at = now()
        where rp.id = previous_active_id;
    end if;

    insert into navigation.route_predictions (
        vessel_id,
        mmsi,
        origin_position_id,
        destination_raw,
        destination_normalized,
        destination_unlocode,
        route_version,
        route_method,
        route_geojson,
        great_circle_distance_nm,
        navigable_distance_nm,
        route_distance_ratio,
        route_created_at,
        route_update_reason,
        status,
        request_id
    )
    values (
        p_vessel_id,
        normalized_mmsi,
        p_origin_position_id,
        p_destination_raw,
        p_destination_normalized,
        p_destination_unlocode,
        next_version,
        p_route_method,
        p_route_geojson,
        p_great_circle_distance_nm,
        p_navigable_distance_nm,
        p_route_distance_ratio,
        now(),
        p_route_update_reason,
        'active',
        p_request_id
    )
    returning id into new_id;

    route_prediction_id := new_id;
    route_version := next_version;
    old_route_prediction_id := previous_active_id;
    inserted := true;
    return next;
end;
$$;

grant usage on schema navigation to service_role;

grant select, insert, update
on table navigation.route_predictions
to service_role;

grant execute
on function navigation.activate_route_prediction(
    uuid,
    text,
    bigint,
    text,
    text,
    text,
    text,
    jsonb,
    double precision,
    double precision,
    double precision,
    text,
    text
)
to service_role;

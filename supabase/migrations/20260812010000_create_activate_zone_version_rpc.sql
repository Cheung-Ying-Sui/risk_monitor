-- Phase 2.6.3: Risk zone version activation RPC.
-- Purpose:
-- - Atomically promote a validated zone version to active.
-- - Supersede any existing active version for the same zone.
-- - Preserve the partial unique index invariant: one active version per zone.

create or replace function risk.activate_zone_version(p_zone_version_id uuid)
returns table (
    zone_id uuid,
    old_zone_version_id uuid,
    new_zone_version_id uuid
)
language plpgsql
volatile
as $$
declare
    target_version risk.zone_versions%rowtype;
    previous_active_id uuid;
begin
    select *
    into target_version
    from risk.zone_versions zv
    where zv.id = p_zone_version_id
    for update;

    if not found then
        raise exception 'risk zone version % does not exist', p_zone_version_id
            using errcode = 'P0002';
    end if;

    if target_version.geometry is null or st_isempty(target_version.geometry) then
        raise exception 'risk zone version % has empty geometry', p_zone_version_id
            using errcode = '22023';
    end if;

    if target_version.status not in ('validated', 'active') then
        raise exception 'risk zone version % status % cannot be activated',
            p_zone_version_id,
            target_version.status
            using errcode = '22023';
    end if;

    perform 1
    from risk.zones z
    where z.id = target_version.zone_id
    for update;

    if not found then
        raise exception 'risk zone % does not exist', target_version.zone_id
            using errcode = 'P0002';
    end if;

    select id
    into previous_active_id
    from risk.zone_versions zv
    where zv.zone_id = target_version.zone_id
      and zv.status = 'active'
      and zv.id <> target_version.id
    for update;

    if previous_active_id is not null then
        update risk.zone_versions
        set status = 'superseded',
            superseded_at = now()
        where zone_versions.id = previous_active_id;
    end if;

    update risk.zone_versions
    set status = 'active',
        activated_at = coalesce(activated_at, now()),
        superseded_at = null
    where zone_versions.id = target_version.id;

    update risk.zones
    set status = 'active',
        updated_at = now()
    where zones.id = target_version.zone_id;

    zone_id := target_version.zone_id;
    old_zone_version_id := previous_active_id;
    new_zone_version_id := target_version.id;
    return next;
end;
$$;

grant execute
on function risk.activate_zone_version(uuid)
to service_role;

-- Phase 2.6.4: Tracking consistency cleanup and active MMSI uniqueness.
-- Purpose:
-- - Repair unambiguous null vessel_id tracking rows where safe.
-- - Disable duplicate active MMSI rows without deleting history.
-- - Enforce one active tracking row per MMSI.

with unique_core_vessels as (
    select
        v.mmsi,
        (array_agg(v.id order by v.id))[1] as vessel_id
    from core.vessels v
    where v.mmsi is not null
    group by v.mmsi
    having count(*) = 1
),
repair_candidates as (
    select
        tv.id as tracked_vessel_id,
        ucv.vessel_id
    from tracking.tracked_vessels tv
    join unique_core_vessels ucv
        on ucv.mmsi = tv.mmsi
    where tv.vessel_id is null
      and not exists (
          select 1
          from tracking.tracked_vessels existing
          where existing.vessel_id = ucv.vessel_id
      )
)
update tracking.tracked_vessels tv
set vessel_id = repair_candidates.vessel_id,
    updated_at = now(),
    metadata = coalesce(tv.metadata, '{}'::jsonb)
        || jsonb_build_object(
            'phase_2_6_4_vessel_id_repaired',
            true,
            'phase_2_6_4_repaired_at',
            now()
        )
from repair_candidates
where tv.id = repair_candidates.tracked_vessel_id;

with ranked_active as (
    select
        tv.*,
        row_number() over (
            partition by tv.mmsi
            order by
                (tv.vessel_id is not null) desc,
                tv.priority desc,
                tv.created_at asc,
                tv.id asc
        ) as active_rank
    from tracking.tracked_vessels tv
    where tv.is_active = true
      and tv.mmsi is not null
),
keepers as (
    select *
    from ranked_active
    where active_rank = 1
),
duplicates as (
    select *
    from ranked_active
    where active_rank > 1
),
duplicate_summary as (
    select
        k.id as keeper_id,
        max(d.priority) as max_duplicate_priority,
        min(d.tracking_interval_minutes) as min_duplicate_interval,
        max(d.monitor_purpose) filter (
            where d.monitor_purpose is not null
        ) as duplicate_monitor_purpose,
        max(d.risk_reason) filter (
            where d.risk_reason is not null
        ) as duplicate_risk_reason,
        to_jsonb(array_agg(d.id order by d.created_at, d.id)) as duplicate_ids
    from keepers k
    join duplicates d
        on d.mmsi = k.mmsi
    group by k.id
)
update tracking.tracked_vessels tv
set priority = greatest(tv.priority, duplicate_summary.max_duplicate_priority),
    tracking_interval_minutes = least(
        tv.tracking_interval_minutes,
        duplicate_summary.min_duplicate_interval
    ),
    monitor_purpose = coalesce(
        tv.monitor_purpose,
        duplicate_summary.duplicate_monitor_purpose
    ),
    risk_reason = coalesce(
        tv.risk_reason,
        duplicate_summary.duplicate_risk_reason
    ),
    updated_at = now(),
    metadata = coalesce(tv.metadata, '{}'::jsonb)
        || jsonb_build_object(
            'phase_2_6_4_merged_duplicate_tracking_ids',
            duplicate_summary.duplicate_ids,
            'phase_2_6_4_merged_at',
            now()
        )
from duplicate_summary
where tv.id = duplicate_summary.keeper_id;

with ranked_active as (
    select
        tv.*,
        first_value(tv.id) over (
            partition by tv.mmsi
            order by
                (tv.vessel_id is not null) desc,
                tv.priority desc,
                tv.created_at asc,
                tv.id asc
        ) as keeper_id,
        row_number() over (
            partition by tv.mmsi
            order by
                (tv.vessel_id is not null) desc,
                tv.priority desc,
                tv.created_at asc,
                tv.id asc
        ) as active_rank
    from tracking.tracked_vessels tv
    where tv.is_active = true
      and tv.mmsi is not null
)
update tracking.tracked_vessels tv
set is_active = false,
    tracking_mode = 'paused',
    updated_at = now(),
    metadata = coalesce(tv.metadata, '{}'::jsonb)
        || jsonb_build_object(
            'phase_2_6_4_disabled_duplicate',
            true,
            'phase_2_6_4_disabled_at',
            now(),
            'phase_2_6_4_merged_into_tracked_vessel_id',
            ranked_active.keeper_id
        )
from ranked_active
where tv.id = ranked_active.id
  and ranked_active.active_rank > 1;

do $$
begin
    if exists (
        select 1
        from tracking.tracked_vessels tv
        where tv.is_active = true
          and tv.mmsi is not null
        group by tv.mmsi
        having count(*) > 1
    ) then
        raise exception 'duplicate active tracked_vessels.mmsi rows remain';
    end if;
end;
$$;

create unique index if not exists tracked_vessels_one_active_mmsi_unique
on tracking.tracked_vessels (mmsi)
where is_active = true
  and mmsi is not null;

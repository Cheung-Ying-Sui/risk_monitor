-- Phase 2.3.6: Upgrade tracked vessels to a risk monitoring strategy model.
-- This migration is additive and preserves existing tracking.tracked_vessels rows.

alter table tracking.tracked_vessels
add column if not exists tracking_mode text default 'history_tracking',
add column if not exists monitor_purpose text,
add column if not exists risk_reason text,
add column if not exists start_time timestamptz,
add column if not exists end_time timestamptz,
add column if not exists metadata jsonb default '{}'::jsonb;

comment on column tracking.tracked_vessels.tracking_mode is
'Monitoring mode. query = temporary real-time query without continuous track recording; history_tracking = regular historical track recording; high_risk_monitoring = high-risk priority monitoring; paused = strategy retained but not scheduled.';

comment on column tracking.tracked_vessels.monitor_purpose is
'Business purpose for monitoring. Examples: insurance_underwriting, war_risk_monitoring, eta_prediction, claims_monitoring.';

comment on column tracking.tracked_vessels.risk_reason is
'Human-readable risk reason explaining why this vessel is monitored.';

comment on column tracking.tracked_vessels.start_time is
'Optional monitoring start time. Null means active immediately when is_active is true.';

comment on column tracking.tracked_vessels.end_time is
'Optional monitoring end time. Null means no scheduled end time.';

comment on column tracking.tracked_vessels.metadata is
'Additional structured metadata for monitoring strategy, risk tags, insurance references, scheduling hints, or model inputs.';

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'tracked_vessels_tracking_mode_check'
          and conrelid = 'tracking.tracked_vessels'::regclass
    ) then
        alter table tracking.tracked_vessels
        add constraint tracked_vessels_tracking_mode_check
        check (
            tracking_mode in (
                'query',
                'history_tracking',
                'high_risk_monitoring',
                'paused'
            )
        )
        not valid;
    end if;
end;
$$;

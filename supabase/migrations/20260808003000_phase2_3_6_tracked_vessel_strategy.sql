-- Phase 2.3.6: Upgrade tracked vessels from a collection list to a monitoring strategy model.
-- This migration is additive and preserves existing tracking.tracked_vessels rows.

alter table tracking.tracked_vessels
add column if not exists tracking_mode text default 'history_tracking',
add column if not exists monitor_purpose text,
add column if not exists risk_reason text,
add column if not exists start_time timestamptz,
add column if not exists end_time timestamptz,
add column if not exists metadata jsonb default '{}'::jsonb;

comment on column tracking.tracked_vessels.tracking_mode is
'Monitoring mode. Suggested values: query, history_tracking, high_risk_monitoring.';

comment on column tracking.tracked_vessels.monitor_purpose is
'Business purpose for monitoring, such as insurance underwriting, claims monitoring, war risk, or route risk analysis.';

comment on column tracking.tracked_vessels.risk_reason is
'Human-readable reason explaining why this vessel is monitored.';

comment on column tracking.tracked_vessels.start_time is
'Optional monitoring start time. Null means active immediately when is_active is true.';

comment on column tracking.tracked_vessels.end_time is
'Optional monitoring end time. Null means no scheduled end time.';

comment on column tracking.tracked_vessels.metadata is
'Additional structured metadata for monitoring strategy, risk tags, policy references, or scheduling hints.';

-- Phase 2.3.1: Preserve legacy dynamic vessel fields in Supabase.
-- This migration is additive and preserves existing vessel position rows.

alter table tracking.vessel_positions
add column if not exists eta text,
add column if not exists draught numeric(6,2);

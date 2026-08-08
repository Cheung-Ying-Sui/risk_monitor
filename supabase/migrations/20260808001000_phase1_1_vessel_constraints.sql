-- Phase 1.1: Production constraints for vessel collection.
-- This migration preserves existing tables and data.

alter table tracking.vessel_positions
add column if not exists source_id uuid;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'vessel_positions_source_id_fkey'
          and conrelid = 'tracking.vessel_positions'::regclass
    ) then
        alter table tracking.vessel_positions
        add constraint vessel_positions_source_id_fkey
        foreign key (source_id)
        references ingest.data_sources(id)
        not valid;
    end if;
end;
$$;

alter table tracking.vessel_positions
alter column vessel_id set not null,
alter column mmsi set not null,
alter column observed_at set not null,
alter column source_id set not null;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'vessel_positions_latitude_range_check'
          and conrelid = 'tracking.vessel_positions'::regclass
    ) then
        alter table tracking.vessel_positions
        add constraint vessel_positions_latitude_range_check
        check (
            latitude is null
            or (
                latitude >= -90
                and latitude <= 90
            )
        )
        not valid;
    end if;

    if not exists (
        select 1
        from pg_constraint
        where conname = 'vessel_positions_longitude_range_check'
          and conrelid = 'tracking.vessel_positions'::regclass
    ) then
        alter table tracking.vessel_positions
        add constraint vessel_positions_longitude_range_check
        check (
            longitude is null
            or (
                longitude >= -180
                and longitude <= 180
            )
        )
        not valid;
    end if;
end;
$$;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'vessel_positions_vessel_observed_source_unique'
          and conrelid = 'tracking.vessel_positions'::regclass
    ) then
        alter table tracking.vessel_positions
        add constraint vessel_positions_vessel_observed_source_unique
        unique (vessel_id, observed_at, source_id);
    end if;
end;
$$;

create index if not exists idx_tracking_vessel_positions_source_observed_at_desc
on tracking.vessel_positions (source_id, observed_at desc);

alter table tracking.tracked_vessels
add column if not exists updated_at timestamptz not null default now();

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'tracked_vessels_vessel_id_unique'
          and conrelid = 'tracking.tracked_vessels'::regclass
    ) then
        alter table tracking.tracked_vessels
        add constraint tracked_vessels_vessel_id_unique
        unique (vessel_id);
    end if;
end;
$$;

create or replace function tracking.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists trg_tracking_tracked_vessels_set_updated_at on tracking.tracked_vessels;

create trigger trg_tracking_tracked_vessels_set_updated_at
before update on tracking.tracked_vessels
for each row
execute function tracking.set_updated_at();

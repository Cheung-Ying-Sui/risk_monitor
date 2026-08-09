-- Phase 2.5.2.4.1: Latest vessel positions view.
-- Purpose:
-- - Provide a unified read entrypoint for the latest known vessel position.
-- - Return only the newest observed position per vessel.

create or replace view tracking.latest_vessel_positions as
select
    vessel_id,
    mmsi,
    latitude,
    longitude,
    sog,
    cog,
    heading,
    destination,
    nav_status,
    observed_at,
    received_at,
    source_id
from (
    select
        vessel_id,
        mmsi,
        latitude,
        longitude,
        sog,
        cog,
        heading,
        destination,
        nav_status,
        observed_at,
        received_at,
        source_id,
        row_number() over (
            partition by vessel_id
            order by observed_at desc, received_at desc, id desc
        ) as row_number
    from tracking.vessel_positions
    where vessel_id is not null
) ranked_positions
where row_number = 1;

comment on view tracking.latest_vessel_positions is
'Latest observed vessel position per vessel, derived from tracking.vessel_positions.';

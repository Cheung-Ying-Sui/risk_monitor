-- Phase 2.5.4.3.4: Extend latest vessel positions view for risk matching.
-- Purpose:
-- - Preserve the existing latest-position semantics and fields.
-- - Expose source position row id and geography point for risk zone matching.

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
    source_id,
    position_id,
    position
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
        id as position_id,
        position,
        row_number() over (
            partition by vessel_id
            order by observed_at desc, received_at desc, id desc
        ) as row_number
    from tracking.vessel_positions
    where vessel_id is not null
) ranked_positions
where row_number = 1;

comment on view tracking.latest_vessel_positions is
'Latest observed vessel position per vessel, derived from tracking.vessel_positions. Includes source position_id and geography position for risk zone matching.';

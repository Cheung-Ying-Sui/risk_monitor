-- Personal non-commercial MVP: keep an approximate port-area point distinct from a verified berth.
alter table public.port_weather_locations
    add column coordinate_system text not null default 'WGS84'
        check (coordinate_system = 'WGS84');

alter table public.port_weather_locations
    drop constraint port_weather_location_verified_check;
alter table public.port_weather_locations
    add constraint port_weather_location_evidence_check check (
        verification_status not in ('verified', 'approximate') or
        (requested_latitude is not null and requested_longitude is not null and
         nullif(trim(coordinate_source), '') is not null and
         nullif(trim(location_description), '') is not null and
         (verification_status = 'approximate' or verified_at is not null))
    );
alter table public.port_weather_locations
    drop constraint port_weather_location_primary_check;
alter table public.port_weather_locations
    add constraint port_weather_location_primary_check
        check (not is_primary or verification_status in ('verified', 'approximate'));
alter table public.port_weather_locations
    drop constraint port_weather_locations_verification_status_check;
alter table public.port_weather_locations
    add constraint port_weather_locations_verification_status_check
        check (verification_status in ('pending_verification', 'approximate', 'verified', 'rejected'));

comment on column public.port_weather_locations.verification_status is
    'approximate = unverified port-area WGS84 point for MVP; verified = reviewed terminal/berth point.';

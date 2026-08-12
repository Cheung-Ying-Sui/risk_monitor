-- Phase 2.6.3: JWLA baseline seed RPC for service-role controlled import.
-- Purpose:
-- - Keep the private risk schema out of the exposed Data API schemas.
-- - Allow the existing service-role Supabase client to submit large GeoJSON.
-- - Insert a validated baseline version only; activation stays in risk.activate_zone_version.

create or replace function tracking.seed_jwla033_baseline(
    p_source text,
    p_source_url text,
    p_source_document text,
    p_document_hash text,
    p_zone_name text,
    p_zone_slug text,
    p_zone_type text,
    p_geometry_geojson jsonb,
    p_raw_text text,
    p_validation_result jsonb,
    p_parser_version text default null
)
returns table (
    source_id uuid,
    source_created boolean,
    zone_id uuid,
    zone_created boolean,
    zone_version_id uuid,
    zone_version_no integer,
    zone_version_status text,
    zone_version_created boolean
)
language plpgsql
volatile
as $$
declare
    existing_source risk.zone_sources%rowtype;
    existing_zone risk.zones%rowtype;
    existing_version risk.zone_versions%rowtype;
    v_source_id uuid;
    v_zone_id uuid;
    next_version_no integer;
begin
    select *
    into existing_source
    from risk.zone_sources zs
    where zs.source = p_source
      and zs.document_hash = p_document_hash
    limit 1;

    if found then
        v_source_id := existing_source.id;
        source_created := false;
    else
        insert into risk.zone_sources (
            source,
            source_url,
            source_document,
            document_hash,
            raw_text,
            parser_version,
            status
        )
        values (
            p_source,
            p_source_url,
            p_source_document,
            p_document_hash,
            p_raw_text,
            p_parser_version,
            'validated'
        )
        returning id into v_source_id;
        source_created := true;
    end if;

    select *
    into existing_zone
    from risk.zones z
    where z.source = p_source
      and z.zone_slug = p_zone_slug
    limit 1;

    if found then
        v_zone_id := existing_zone.id;
        zone_created := false;
    else
        insert into risk.zones (
            zone_name,
            zone_slug,
            zone_type,
            source,
            description,
            status
        )
        values (
            p_zone_name,
            p_zone_slug,
            p_zone_type,
            p_source,
            p_raw_text,
            'validated'
        )
        returning id into v_zone_id;
        zone_created := true;
    end if;

    select *
    into existing_version
    from risk.zone_versions zv
    where zv.zone_id = v_zone_id
      and zv.source_id = v_source_id
      and zv.raw_extraction ->> 'source_document' = p_source_document
      and zv.raw_extraction ->> 'document_hash' = p_document_hash
      and zv.raw_extraction ->> 'seed_slug' = p_zone_slug
    limit 1;

    if found then
        zone_version_id := existing_version.id;
        zone_version_no := existing_version.version_no;
        zone_version_status := existing_version.status;
        zone_version_created := false;
    else
        select coalesce(max(zv.version_no), 0) + 1
        into next_version_no
        from risk.zone_versions zv
        where zv.zone_id = v_zone_id;

        insert into risk.zone_versions (
            v_zone_id,
            v_source_id,
            version_no,
            effective_date,
            geometry,
            raw_text,
            raw_extraction,
            validation_result,
            confidence,
            status
        )
        values (
            zone_id,
            source_id,
            next_version_no,
            current_date,
            st_multi(
                st_setsrid(
                    st_geomfromgeojson(p_geometry_geojson::text),
                    4326
                )
            )::geometry(MultiPolygon, 4326),
            p_raw_text,
            jsonb_build_object(
                'source_document',
                p_source_document,
                'document_hash',
                p_document_hash,
                'seed_slug',
                p_zone_slug,
                'baseline_path',
                'JWLA_033/JWLA_033_Risk_Seas_Merge_Layer.json'
            ),
            p_validation_result,
            null,
            'validated'
        )
        returning id, version_no, status
        into zone_version_id, zone_version_no, zone_version_status;
        zone_version_created := true;
    end if;

    source_id := v_source_id;
    zone_id := v_zone_id;
    return next;
end;
$$;

revoke all
on function tracking.seed_jwla033_baseline(
    text,
    text,
    text,
    text,
    text,
    text,
    text,
    jsonb,
    text,
    jsonb,
    text
)
from public, anon, authenticated;

grant execute
on function tracking.seed_jwla033_baseline(
    text,
    text,
    text,
    text,
    text,
    text,
    text,
    jsonb,
    text,
    jsonb,
    text
)
to service_role;

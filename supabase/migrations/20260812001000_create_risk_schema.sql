-- Phase 2.5.4.3.4: Risk schema foundation.
-- Purpose:
-- - Create a dedicated schema for risk zone source, geometry, versioning, and match data.
-- - Depends on pgcrypto and postgis created by earlier base migrations.

create schema if not exists risk;

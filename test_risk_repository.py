from pathlib import Path


RPC_MIGRATION = Path("supabase/migrations/20260812009000_create_risk_spatial_matching_rpc.sql")
REPOSITORY = Path("risk_repository.py")


def test_rpc_migration_static_sql():
    sql = RPC_MIGRATION.read_text(encoding="utf-8").lower()
    assert "create or replace function risk.match_vessel_current_position" in sql
    assert "create or replace function risk.match_tracked_vessels_current_positions" in sql
    assert "create or replace function risk.record_current_tracked_vessel_risk_matches" in sql
    assert "st_intersects" in sql
    assert "lp.position::geometry" in sql
    assert "on conflict (position_id, zone_version_id, match_type)" in sql
    assert "'intersects'" in sql
    assert "where tv.is_active = true" in sql


def test_repository_static_api():
    source = REPOSITORY.read_text(encoding="utf-8")
    assert "def get_active_risk_zones" in source
    assert "def get_active_risk_zones_geojson" in source
    assert "def get_vessel_current_risk" in source
    assert "def get_tracked_vessels_in_risk_zones" in source
    assert "def record_current_risk_matches" in source
    assert ".rpc(" in source
    assert "get_active_risk_zones_geojson" in source
    assert "match_vessel_current_position" in source


def main():
    test_rpc_migration_static_sql()
    test_repository_static_api()
    print("risk repository static tests passed")


if __name__ == "__main__":
    main()

import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest

from ukmto.models import RunResult

MODULE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fetch_ukmto_incidents", MODULE / "scripts/fetch_ukmto_incidents.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def test_dry_run_without_database_credentials(monkeypatch):
    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **kw: None)
    for name in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    client = Mock()
    monkeypatch.setattr(cli, "UKMTOClient", lambda settings: client)
    service = Mock()
    service.run.return_value = RunResult()
    factory = Mock(return_value=service)
    monkeypatch.setattr(cli, "UKMTOService", factory)
    assert cli.main(["--dry-run"]) == 0
    factory.assert_called_once_with(client, None)
    client.close.assert_called_once()


@pytest.mark.parametrize("args", [["--max-incidents", "0"], ["--max-incidents", "invalid"], []])
def test_configuration_exit_code(monkeypatch, args):
    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **kw: None)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    assert cli.main(args) == 1

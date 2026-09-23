from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ukmto.client import FetchError, LIST_URL
from ukmto.models import FetchedPage
from ukmto.repository import RepositoryError, SupabaseIncidentRepository
from ukmto.service import UKMTOService

NOW = datetime(2026, 9, 22, 10, tzinfo=timezone.utc)
URL = "https://www.ukmto.org/recent-incidents/report-141"


class MemoryRepository:
    """Test double only. Production deduplication uses the transactional SQL RPC."""
    def __init__(self):
        self.rows = {}
        self.history = set()

    def save(self, incident, observed_at):
        previous = self.rows.get(incident.external_id)
        action = "inserted" if previous is None else "unchanged" if previous == incident.content_hash else "updated"
        self.rows[incident.external_id] = incident.content_hash
        self.history.add((incident.external_id, incident.content_hash))
        return action


def make_client(markup, second=False):
    listing = "<main><a href='/recent-incidents/report-141'>Attack</a>"
    if second:
        listing += "<a href='/recent-incidents/report-142'>Advisory</a>"
    listing += "</main>"
    pages = {LIST_URL: FetchedPage(LIST_URL, listing, NOW), URL: FetchedPage(URL, markup, NOW)}
    client = Mock()
    def fetch(url):
        if url not in pages:
            raise FetchError("HTTP 404")
        return pages[url]
    client.fetch.side_effect = fetch
    return client


def test_insert_repeat_update(attack_html):
    repo = MemoryRepository()
    first = UKMTOService(make_client(attack_html), repo).run()
    repeated = UKMTOService(make_client(attack_html), repo).run()
    changed = UKMTOService(make_client(attack_html.replace("All crew are safe", "Crew status pending")), repo).run()
    assert first.inserted_count == 1
    assert repeated.unchanged_count == 1
    assert changed.updated_count == 1
    assert len(repo.rows) == 1 and len(repo.history) == 2
    assert first.exit_code == repeated.exit_code == changed.exit_code == 0


def test_single_failure_continues(attack_html):
    repo = MemoryRepository()
    result = UKMTOService(make_client(attack_html, second=True), repo).run()
    assert result.inserted_count == result.failed_count == 1
    assert result.exit_code == 4
    assert result.finished_at is not None


def test_dry_run_never_uses_repository(attack_html):
    repo, callback = Mock(), Mock()
    result = UKMTOService(make_client(attack_html), repo).run(dry_run=True, on_parsed=callback)
    repo.save.assert_not_called()
    callback.assert_called_once()
    assert result.parsed_count == 1 and result.inserted_count == 0


def test_database_failure_status(attack_html):
    repo = Mock()
    repo.save.side_effect = RepositoryError("database unavailable")
    result = UKMTOService(make_client(attack_html), repo).run()
    assert result.database_failed_count == result.failed_count == 1
    assert result.exit_code == 3


def test_list_failure():
    client = Mock()
    client.fetch.side_effect = FetchError("HTTP 403")
    result = UKMTOService(client).run(dry_run=True)
    assert result.exit_code == 2


def test_max_incidents(attack_html):
    result = UKMTOService(make_client(attack_html, second=True)).run(dry_run=True, max_incidents=1)
    assert result.fetched_count == result.parsed_count == 1 and result.failed_count == 0


def test_rpc_uses_transaction_and_propagates_error(attack_html):
    from ukmto.parser import parse_incident
    incident = parse_incident(attack_html, URL)
    client = Mock()
    client.rpc.return_value.execute.return_value = SimpleNamespace(data="inserted")
    repo = SupabaseIncidentRepository(client)
    assert repo.save(incident, NOW) == "inserted"
    client.rpc.assert_called_with("ingest_ukmto_incident", {"p_incident": incident.payload(), "p_observed_at": NOW.isoformat()})
    client.rpc.return_value.execute.side_effect = RuntimeError("secret SDK headers")
    with pytest.raises(RepositoryError, match="RuntimeError") as caught:
        repo.save(incident, NOW)
    assert "secret SDK headers" not in str(caught.value)

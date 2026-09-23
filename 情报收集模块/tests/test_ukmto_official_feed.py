import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from ukmto.client import FEED_URL, LIST_URL, FetchError, UKMTOClient
from ukmto.config import Settings
from ukmto.models import FetchedFeed, FetchedPage, utcnow
from ukmto.parser import (ParseError, extract_incident_links, feed_records, has_dynamic_incidents,
                          parse_feed_incident)
from ukmto.service import UKMTOService

FIXTURES = Path(__file__).parent / "fixtures"
LIVE_HTML = (FIXTURES / "recent_incidents_live.html").read_text()
LIVE_ROWS = json.loads((FIXTURES / "incidents_live.json").read_text())


def test_real_html_placeholder_is_not_an_empty_list():
    assert has_dynamic_incidents(LIVE_HTML)
    with pytest.raises(ParseError, match="placeholder"):
        extract_incident_links(LIVE_HTML, LIST_URL)


def test_all_real_reports_parse_and_have_unique_ids():
    parsed = [parse_feed_incident(row) for row in feed_records(LIVE_ROWS)]
    assert len(parsed) == 61
    assert len({row.external_id for row in parsed}) == 61
    first = parse_feed_incident(LIVE_ROWS[0])
    assert first.external_id == "UKMTO-2026-78"
    assert first.incident_type == "suspicious_activity"
    assert first.location_text == "85NM south of Balhaf, Yemen"
    assert first.location_precision == "approximate"
    assert first.latitude == 12.6
    assert first.source_type == "master"
    assert first.raw_payload["record"] == LIVE_ROWS[0]
    assert first.source_url == LIST_URL + "#" + LIVE_ROWS[0]["sitecoreId"]


def test_missing_values_remain_missing():
    row = {**LIVE_ROWS[0], "otherDetails": "An incident was reported.", "utcDateOfIncident": None,
           "utcDateCreated": None, "locationLatitude": None, "locationLongitude": None, "incidentNumber": None}
    parsed = parse_feed_incident(row)
    assert parsed.incident_time is parsed.published_at is parsed.latitude is parsed.longitude is None
    assert len(parsed.external_id) == 64
    assert parsed.location_text == "Gulf of Aden"
    assert parsed.location_precision == "region"


def test_revision_hash_and_annual_id():
    original = parse_feed_incident(LIVE_ROWS[0])
    update = parse_feed_incident({**LIVE_ROWS[0], "otherDetails": LIVE_ROWS[0]["otherDetails"] + "\nUPDATE 001: Authorities investigating."})
    assert original.external_id == update.external_id
    assert update.raw_payload["update_number"] == 1
    assert original.content_hash != update.content_hash
    next_year = {key: value.replace("2026", "2027").replace("078-26", "078-27") if isinstance(value, str) else value for key, value in LIVE_ROWS[0].items()}
    assert parse_feed_incident(next_year).external_id == "UKMTO-2027-78"
    assert parse_feed_incident({**LIVE_ROWS[0], "crewHeld": 1}).content_hash != original.content_hash


@pytest.mark.parametrize("lat,lon", [(None, 15), ("bad", 15), ("NaN", 15), (91, 15), (12, 181)])
def test_invalid_feed_coordinates(lat, lon):
    parsed = parse_feed_incident({**LIVE_ROWS[0], "locationLatitude": lat, "locationLongitude": lon})
    assert parsed.latitude is parsed.longitude is None


def test_dynamic_service_and_per_record_failure():
    client = Mock()
    client.fetch.return_value = FetchedPage(LIST_URL, LIVE_HTML, utcnow())
    client.fetch_feed.return_value = FetchedFeed(FEED_URL, [LIVE_ROWS[0], {**LIVE_ROWS[1], "otherDetails": ""}], utcnow())
    callback = Mock()
    result = UKMTOService(client).run(dry_run=True, on_parsed=callback)
    assert result.fetched_count == 2
    assert result.parsed_count == result.failed_count == 1
    assert result.exit_code == 4
    client.fetch.assert_called_once_with(LIST_URL)
    client.fetch_feed.assert_called_once_with()


def test_bad_feed_structure_and_failure():
    with pytest.raises(ParseError):
        feed_records({"error": "unavailable"})
    client = Mock()
    client.fetch.return_value = FetchedPage(LIST_URL, LIVE_HTML, utcnow())
    client.fetch_feed.side_effect = FetchError("HTTP 503")
    assert UKMTOService(client).run(dry_run=True).exit_code == 2


def test_client_reads_official_feed_without_auth():
    session = Mock(headers={})
    response = Mock(status_code=200, headers={"Content-Type": "application/json"})
    response.json.return_value = LIVE_ROWS
    session.get.return_value = response
    client = UKMTOClient(Settings(), session=session)
    assert client.fetch_feed().data == LIVE_ROWS
    session.get.assert_called_once_with(FEED_URL, timeout=30, allow_redirects=False)


def test_non_ukmto_records_excluded():
    assert feed_records([{**LIVE_ROWS[0], "incidentIssuer": "OTHER"}]) == []

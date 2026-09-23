from datetime import datetime, timezone
from pathlib import Path

import pytest

from ukmto.parser import (ParseError, content_hash, extract_incident_links, normalize_url,
                          parse_coordinates, parse_datetime, parse_incident)

URL = "https://www.ukmto.org/recent-incidents/report-141"


def test_attack_and_missing_coordinates(attack_html):
    row = parse_incident(attack_html, URL)
    assert row.external_id == "UKMTO-141"
    assert row.incident_type == "attack"
    assert row.incident_time == datetime(2026, 9, 22, 8, 30, tzinfo=timezone.utc)
    assert row.published_at.hour == 9
    assert row.location_text == "75NM east of Aden, Yemen"
    assert row.location_precision == "approximate"
    assert row.latitude is row.longitude is None
    assert "All crew are safe" in row.description
    assert "Cookie" not in row.description
    assert row.raw_payload["html"] == attack_html


@pytest.mark.parametrize("label,expected", [("Suspicious Activity", "suspicious_activity"),
    ("Hijack", "hijack"), ("Advisory", "advisory"), ("Military Interaction", "military_interaction"),
    ("Unclassified Report", "unknown")])
def test_incident_types(attack_html, label, expected):
    assert parse_incident(attack_html.replace("Attack", label), URL).incident_type == expected


def test_stable_url_fallback_and_fragment(attack_html):
    markup = attack_html.replace("UKMTO #141 - ", "")
    a = parse_incident(markup, URL + "?utm_source=x")
    b = parse_incident(markup, URL)
    assert a.external_id == b.external_id and len(a.external_id) == 64
    assert a.incident_number is None
    assert a.raw_payload["warnings"] == ["missing_incident_number_url_hash_used"]
    assert normalize_url(URL + "#event1") != normalize_url(URL + "#event2")


def test_missing_dates_are_null(attack_html):
    markup = attack_html.replace("Incident time:", "Unlabelled time:").replace("Published:", "Unlabelled date:")
    row = parse_incident(markup, URL)
    assert row.incident_time is row.published_at is None


def test_update_and_year_number(attack_html):
    original = parse_incident(attack_html.replace("#141", "#2026/141"), URL)
    update = parse_incident(attack_html.replace("#141", "#2026/141").replace("Attack", "Attack Update 001"), URL + "-update")
    assert original.external_id == update.external_id == "UKMTO-2026-141"
    assert update.content_hash != original.content_hash
    assert update.raw_payload["update_number"] == 1


def test_hash_stable_against_format_and_tracking(attack_html):
    first = parse_incident(attack_html, URL)
    other = parse_incident(attack_html.replace("All crew", "All   crew").replace("<p>", "<p class='new'>"), URL + "?utm_medium=x")
    assert first.content_hash == other.content_hash
    first.raw_payload["fetched_at"] = "different"
    assert first.content_hash == content_hash(first)


@pytest.mark.parametrize("markup", ["", "<main><h1>Attack</h1></main>", "<p>nothing</p>",
    "<title>Attention Required! | Cloudflare</title><h1>blocked</h1>",
    "<main><h1>Recent Incidents</h1><p>0 reports</p></main>"])
def test_incomplete_or_blocked_detail_raises(markup):
    with pytest.raises(ParseError):
        parse_incident(markup, URL)


def test_list_semantics_and_deduplication():
    markup = (Path(__file__).parent / "fixtures/list.html").read_text()
    links = extract_incident_links(markup, "https://www.ukmto.org/recent-incidents")
    assert [link.url for link in links] == [URL, URL.replace("141", "142")]
    assert extract_incident_links("<main><h1>Recent Incidents</h1><p>0 reports</p></main>", URL) == []
    with pytest.raises(ParseError):
        extract_incident_links("<main><h1>Recent Incidents</h1><div>Loading...</div></main>", URL)


def test_inline_anchor():
    markup = "<main><a href='#event-7'>UKMTO #7</a><article id='event-7'><h2>UKMTO #7 - Advisory</h2><p>Report body</p></article></main>"
    links = extract_incident_links(markup, URL)
    assert len(links) == 1
    assert parse_incident(markup, links[0].url).incident_type == "advisory"
    with pytest.raises(ParseError):
        parse_incident(markup, URL + "#missing")


@pytest.mark.parametrize("text,expected", [
    ("12.5N, 45.25E", (12.5, 45.25)),
    ("12°30'N 045°15'E", (12.5, 45.25)),
    ('12°30\'00"S, 045°15\'00"W', (-12.5, -45.25)),
    ("Latitude: 0 Longitude: 0", (0, 0)),
    ("Latitude: -12.5 Longitude: 45.25", (-12.5, 45.25)),
    ("91N, 45E", (None, None)), ("12N, 181E", (None, None)),
    ("12°75'N 045°15'E", (None, None)),
    ("75NM east of Aden", (None, None)),
])
def test_coordinates(text, expected):
    assert parse_coordinates(text) == expected


@pytest.mark.parametrize("text", ["2026-09-22T08:30:00Z", "22/09/2026 08:30", "22 Sep 2026 0830 UTC", "220830Z SEP 2026"])
def test_date_formats(text):
    assert parse_datetime(text) == datetime(2026, 9, 22, 8, 30, tzinfo=timezone.utc)


def test_bad_date_retained_and_warned(attack_html):
    row = parse_incident(attack_html.replace("22 September 2026 09:00 UTC", "not a date"), URL)
    assert row.published_at is None
    assert row.raw_payload["raw_dates"]["published_at"] == "not a date"
    assert "unparsed_published_at" in row.raw_payload["warnings"]

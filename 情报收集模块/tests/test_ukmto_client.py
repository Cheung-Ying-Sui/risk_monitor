from unittest.mock import Mock

import pytest
import requests

from ukmto.client import FetchError, LIST_URL, UKMTOClient
from ukmto.config import ConfigurationError, Settings
from ukmto.logging_utils import JsonFormatter, redact


def response(status=200, content_type="text/html", location=None):
    return Mock(status_code=status, text="<main>Report</main>", headers={"Content-Type": content_type, **({"Location": location} if location else {})})


def client_with(*replies, retries=3):
    session = Mock(headers={})
    session.get.side_effect = replies
    sleep = Mock()
    return UKMTOClient(Settings(retries=retries), session=session, sleep=sleep, clock=lambda: 10), session, sleep


def test_network_and_server_retry_then_success():
    client, session, sleep = client_with(requests.Timeout(), response(503), response())
    assert client.fetch(LIST_URL).html == "<main>Report</main>"
    assert session.get.call_count == 3
    assert 2 in [call.args[0] for call in sleep.call_args_list]
    assert session.get.call_args.kwargs["timeout"] == 30
    assert session.headers["User-Agent"].startswith("RiskMonitor")


@pytest.mark.parametrize("status", [400, 403, 404, 429])
def test_client_errors_are_not_retried(status):
    client, session, _ = client_with(response(status))
    with pytest.raises(FetchError, match=str(status)):
        client.fetch(LIST_URL)
    assert session.get.call_count == 1


def test_retries_are_bounded():
    client, session, _ = client_with(response(500), response(500), retries=1)
    with pytest.raises(FetchError, match="after retries"):
        client.fetch(LIST_URL)
    assert session.get.call_count == 2


def test_redirect_and_throttle():
    client, session, sleep = client_with(response(302, location="/incidents/141"), response())
    assert client.fetch(LIST_URL).url == "https://www.ukmto.org/incidents/141"
    sleep.assert_called_with(1)
    assert session.get.call_args.kwargs["allow_redirects"] is False


def test_external_redirect_is_rejected():
    client, session, _ = client_with(response(302, location="https://other.example/incidents/141"))
    with pytest.raises(FetchError, match="official UKMTO"):
        client.fetch(LIST_URL)
    assert session.get.call_count == 1


def test_pdf_not_parsed_as_html():
    client, _, _ = client_with(response(content_type="application/pdf"))
    with pytest.raises(FetchError, match="Expected HTML"):
        client.fetch(LIST_URL)


@pytest.mark.parametrize("key,value", [("UKMTO_REQUEST_RETRIES", "-1"), ("UKMTO_REQUEST_RETRIES", "99"),
    ("UKMTO_REQUEST_TIMEOUT_SECONDS", "nan"), ("UKMTO_REQUEST_TIMEOUT_SECONDS", "0"),
    ("UKMTO_MAX_INCIDENTS_PER_RUN", "0"), ("UKMTO_REQUEST_INTERVAL_SECONDS", "0"),
    ("UKMTO_POLL_INTERVAL_MINUTES", "bad")])
def test_invalid_environment(monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(ConfigurationError):
        Settings.from_env()


def test_log_redaction(monkeypatch):
    import json
    import logging
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "sample-sensitive-service-key")
    record = logging.LogRecord("ukmto", logging.ERROR, "", 1, "ukmto_incident_failed", (), None)
    record.fields = {"message": "sample-sensitive-service-key", "exception_type": "RuntimeError"}
    output = JsonFormatter().format(record)
    assert "sample-sensitive-service-key" not in output
    assert "[REDACTED]" in output
    assert "session=abc" not in redact("Cookie: session=abc")
    record.fields = {"message": "Authorization: Bearer sample-secret"}
    assert json.loads(JsonFormatter().format(record))["message"] == "Authorization=[REDACTED]"

from datetime import datetime, timedelta, timezone

import pytest

from risk_monitor.insurance_tracking_service import InsuranceTrackingService, MmsiSourceUnavailableError, MmsiVerificationError
from risk_monitor import brave_search_client, datalastic_client, deepseek_mmsi_resolver


class FakeGateway:
    def __init__(self, vessel=None, provider_data=None, tracking=None, position=None, mmsi_candidates=None, chinaports_data=None, chinaports_error=None):
        self.vessel = vessel
        self.provider_data = provider_data
        self.tracking = tracking
        self.position = position
        self.activated = []
        self.onboarded = []
        self.saved = []
        self.fetched = []
        self.mmsi_candidates = mmsi_candidates or []
        self.chinaports_data = chinaports_data
        self.chinaports_error = chinaports_error
        self.chinaports_calls = []
        self.owned_shipments = []
        self.prediction_refreshes = []

    def get_vessel_by_imo(self, imo):
        return self.vessel

    def get_vessel_by_mmsi(self, mmsi):
        return self.vessel if self.vessel and self.vessel.get("mmsi") == mmsi else None

    def get_tracking_status(self, vessel_id):
        return self.tracking

    def get_latest_position(self, vessel_id):
        return self.position

    def activate(self, vessel):
        self.activated.append(vessel)
        return {"is_active": True}

    def fetch_by_imo(self, imo):
        self.fetched.append(imo)
        return self.provider_data

    def suggest_mmsi(self, imo, vessel_name):
        return self.mmsi_candidates

    def fetch_by_mmsi(self, mmsi):
        self.chinaports_calls.append(mmsi)
        if self.chinaports_error:
            raise self.chinaports_error
        return self.chinaports_data

    def fetch_chinaports_by_imo(self, imo):
        self.chinaports_calls.append(imo)
        if self.chinaports_error:
            raise self.chinaports_error
        return self.chinaports_data

    def onboard(self, candidate):
        self.onboarded.append(candidate)
        return {"id": "vessel-new", "is_tracked": True, "latest_position": candidate.get("latest_position")}

    def mark_insurance_tracking_owned(self, shipment):
        self.owned_shipments.append(shipment["id"])

    def save_position(self, vessel_id, mmsi, position):
        self.saved.append((vessel_id, mmsi, position))

    def refresh_insurance_prediction(self, vessel_id, mmsi):
        self.prediction_refreshes.append((vessel_id, mmsi))


def test_local_imo_activates_tracking_without_external_provider():
    vessel = {"id": "vessel-1", "mmsi": "636123456", "imo": "9127136"}
    gateway = FakeGateway(vessel=vessel)
    service = InsuranceTrackingService(gateway, provider_configured=False, candidate_configured=False)
    assert service.sync_imo("9127136") == "tracking"
    assert gateway.activated == [vessel]
    assert gateway.fetched == []


def test_imo_only_without_provider_is_not_mistaken_for_live_ais():
    gateway = FakeGateway()
    service = InsuranceTrackingService(gateway, provider_configured=False, candidate_configured=False)
    assert service.sync_imo("9127136") == "ais_provider_not_configured"
    assert service.status_for("9127136") == "awaiting_imo_match"
    assert gateway.onboarded == []


def test_provider_imo_lookup_onboards_and_saves_real_position():
    gateway = FakeGateway(provider_data={
        "imo": "9127136", "mmsi": "636123456", "name": "WADI ALKARNAK",
        "lat": 15.5, "lon": 42.5, "last_position_UTC": "2026-10-10T01:00:00Z",
        "speed": 12.2, "course": 180,
    })
    service = InsuranceTrackingService(gateway, provider_configured=True, candidate_configured=False)
    assert service.sync_imo("9127136") == "tracking"
    assert gateway.fetched == ["9127136"]
    assert gateway.onboarded[0]["mmsi"] == "636123456"
    assert gateway.saved[0][2]["latitude"] == 15.5
    assert gateway.saved[0][2]["observed_at"] == "2026-10-10T01:00:00+00:00"


def test_provider_imo_mismatch_never_onboards():
    gateway = FakeGateway(provider_data={"imo": "9999999", "mmsi": "636123456"})
    service = InsuranceTrackingService(gateway, provider_configured=True, candidate_configured=False)
    assert service.sync_imo("9127136") == "imo_mismatch"
    assert gateway.onboarded == []


def test_active_tracking_without_position_has_distinct_status():
    gateway = FakeGateway(vessel={"id": "vessel-1", "mmsi": "636123456"}, tracking={"is_active": True})
    service = InsuranceTrackingService(gateway, provider_configured=False, candidate_configured=False)
    assert service.status_for("9127136") == "awaiting_position"
    gateway.position = {"observed_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()}
    assert service.status_for("9127136") == "stale_position"


def test_datalastic_key_is_sent_in_header_not_url(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"imo": "9127136", "mmsi": "636123456"}}

    def fake_get(url, **kwargs):
        captured.update(url=url, **kwargs)
        return FakeResponse()

    monkeypatch.setenv("DATALASTIC_API_KEY", "test-secret")
    monkeypatch.setattr(datalastic_client.requests, "get", fake_get)
    assert datalastic_client.fetch_vessel_by_imo("9127136")["mmsi"] == "636123456"
    assert captured["params"] == {"imo": "9127136"}
    assert captured["headers"]["x-api-key"] == "test-secret"
    assert "test-secret" not in captured["url"]


def test_deepseek_candidate_requires_human_confirmation_before_onboarding():
    gateway = FakeGateway(mmsi_candidates={"mmsi": "636123456", "source_url": "https://example.test/vessel", "source_title": "Vessel"}, chinaports_data={
        "mmsi": "636123456", "imo": "9127136", "shipname": "WADI ALKARNAK",
        "latitude": "N 15度30.0000分", "longitude": "E 42度30.0000分",
        "timeStamp": "2026-10-10 09:00(UTC+8)",
    })
    service = InsuranceTrackingService(gateway, provider_configured=False, candidate_configured=True)
    assert service.suggest_mmsi("9127136", "Wadi Alkarnak")["mmsi"] == "636123456"
    assert service.sync_imo("9127136", "Wadi Alkarnak") == "mmsi_confirmation_required"
    assert gateway.chinaports_calls == []
    assert gateway.onboarded == []
    assert service.sync_imo("9127136", "Wadi Alkarnak", "636123456") == "tracking"
    assert gateway.chinaports_calls == ["636123456"]
    assert gateway.onboarded[0]["imo"] == "9127136"
    assert gateway.onboarded[0]["latest_position"]["latitude"] == 15.5


def test_deepseek_candidate_with_wrong_imo_is_never_saved():
    gateway = FakeGateway(mmsi_candidates=["636123456"], chinaports_data={
        "mmsi": "636123456", "imo": "9999999", "shipname": "OTHER SHIP",
    })
    service = InsuranceTrackingService(gateway, provider_configured=False, candidate_configured=True)
    with pytest.raises(MmsiVerificationError):
        service.validate_confirmed_shipments([{"imo_number": "9127136", "extra_data": {"mmsi_candidate": "636123456", "mmsi_confirmed": True}}])
    assert service.sync_imo("9127136", confirmed_mmsi="636123456") == "mmsi_unverified"
    assert gateway.onboarded == []


def test_chinaports_failure_does_not_store_model_candidate():
    gateway = FakeGateway(mmsi_candidates=["636123456"], chinaports_error=RuntimeError("unavailable"))
    service = InsuranceTrackingService(gateway, provider_configured=False, candidate_configured=True)
    with pytest.raises(MmsiSourceUnavailableError):
        service.validate_confirmed_shipments([{"imo_number": "9127136", "extra_data": {"mmsi_candidate": "636123456", "mmsi_confirmed": True}}])
    assert service.sync_imo("9127136", confirmed_mmsi="636123456") == "verification_source_unavailable"
    assert gateway.onboarded == []


def test_deepseek_resolver_requires_real_search_configuration(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.setattr(deepseek_mmsi_resolver.requests, "post", lambda *args, **kwargs: pytest.fail("DeepSeek must not guess without web search"))
    with pytest.raises(deepseek_mmsi_resolver.DeepSeekMmsiError, match="BRAVE_SEARCH_API_KEY"):
        deepseek_mmsi_resolver.suggest_mmsi("9127136")


def test_deepseek_resolver_accepts_only_cited_search_evidence(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test-search-key")
    calls = []
    evidence = [{"url": "https://example.test/imo/9127136", "title": "WADI AL KARNAK", "description": "IMO 9127136 MMSI 622121425", "extra_snippets": ""}]
    monkeypatch.setattr(brave_search_client, "search_vessel_mmsi", lambda imo, name: evidence)

    def fake_chat(api_key, body):
        calls.append(body)
        if len(calls) == 1:
            return {"content": None, "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "search_vessel_mmsi", "arguments": '{"imo":"9127136"}'}}]}
        return {"content": '{"mmsi":"622121425","source_url":"https://example.test/imo/9127136"}'}

    monkeypatch.setattr(deepseek_mmsi_resolver, "_chat", fake_chat)
    assert deepseek_mmsi_resolver.suggest_mmsi("9127136")["mmsi"] == "622121425"
    assert calls[0]["tool_choice"]["function"]["name"] == "search_vessel_mmsi"
    assert calls[1]["messages"][-1]["role"] == "tool"

    calls.clear()
    evidence[0]["description"] = "IMO 9127136 MMSI 622121425"
    def fake_wrong_chat(api_key, body):
        calls.append(body)
        if len(calls) == 1:
            return {"content": None, "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "search_vessel_mmsi", "arguments": '{"imo":"9127136"}'}}]}
        return {"content": '{"mmsi":"622123456","source_url":"https://example.test/imo/9127136"}'}
    monkeypatch.setattr(deepseek_mmsi_resolver, "_chat", fake_wrong_chat)
    assert deepseek_mmsi_resolver.suggest_mmsi("9127136") is None

    calls.clear()
    evidence[0]["description"] = "No vessel identifiers in this snippet"
    evidence[0]["url"] = "https://example.test/imo/9127136/mmsi/622121425"
    def fake_url_only_chat(api_key, body):
        calls.append(body)
        if len(calls) == 1:
            return {"content": None, "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "search_vessel_mmsi", "arguments": '{"imo":"9127136"}'}}]}
        return {"content": '{"mmsi":"622121425","source_url":"https://example.test/imo/9127136/mmsi/622121425"}'}
    monkeypatch.setattr(deepseek_mmsi_resolver, "_chat", fake_url_only_chat)
    assert deepseek_mmsi_resolver.suggest_mmsi("9127136") is None


def test_brave_search_uses_api_not_webpage_scraping(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"web": {"results": [{"title": "WADI AL KARNAK", "url": "https://example.test/ship", "description": "IMO 9127136 MMSI 622121425"}]}}

    def fake_get(url, **kwargs):
        captured.update(url=url, **kwargs)
        return FakeResponse()

    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test-search-key")
    monkeypatch.setattr(brave_search_client.requests, "get", fake_get)
    assert brave_search_client.search_vessel_mmsi("9127136")[0]["url"] == "https://example.test/ship"
    assert captured["url"] == "https://api.search.brave.com/res/v1/web/search"
    assert captured["headers"]["X-Subscription-Token"] == "test-search-key"


def test_confirmed_shipment_tracks_by_imo_without_manual_mmsi():
    gateway = FakeGateway(chinaports_data={
        "imo": "9127136", "mmsi": "636123456", "shipname": "WADI ALKARNAK",
        "latitude": "N 15度30.0000分", "longitude": "E 42度30.0000分",
        "timeStamp": "2026-10-10 09:00(UTC+8)",
    })
    service = InsuranceTrackingService(gateway, provider_configured=False, candidate_configured=False)
    service.sync_shipments([{"imo_number": "9127136"}, {"imo_number": "9127136"}])
    assert gateway.chinaports_calls == ["9127136"]
    assert gateway.onboarded[0]["source"] == "chinaports"
    assert gateway.onboarded[0]["latest_position"]["latitude"] == 15.5
    assert gateway.prediction_refreshes == [("vessel-new", "636123456")]


def test_imo_mismatch_never_onboards_from_chinaports():
    gateway = FakeGateway(chinaports_data={"imo": "9999999", "mmsi": "636123456", "shipname": "OTHER"})
    InsuranceTrackingService(gateway, provider_configured=False, candidate_configured=False).sync_shipments([{"imo_number": "9127136"}])
    assert gateway.chinaports_calls == ["9127136"]
    assert gateway.onboarded == []


def test_new_insurance_tracking_records_ownership_but_existing_manual_tracking_does_not():
    raw = {"imo": "9127136", "mmsi": "636123456", "shipname": "WADI ALKARNAK"}
    new_gateway = FakeGateway(chinaports_data=raw)
    InsuranceTrackingService(new_gateway, provider_configured=False, candidate_configured=False).sync_shipments(
        [{"id": "s1", "imo_number": "9127136"}])
    assert new_gateway.owned_shipments == ["s1"]

    existing_gateway = FakeGateway(vessel={"id": "v1", "mmsi": "636123456", "imo": "9127136"},
                                   tracking={"is_active": True, "tracking_mode": "history_tracking"}, chinaports_data=raw)
    InsuranceTrackingService(existing_gateway, provider_configured=False, candidate_configured=False).sync_shipments(
        [{"id": "s2", "imo_number": "9127136"}])
    assert existing_gateway.owned_shipments == []

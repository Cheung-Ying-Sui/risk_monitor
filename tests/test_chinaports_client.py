import pytest

from risk_monitor import chinaports_client as client


def setup_search(monkeypatch, rows, details):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return rows

    calls = []
    def post(url, **kwargs):
        calls.append(kwargs["data"])
        return Response()
    monkeypatch.setattr(client.requests, "post", post)
    monkeypatch.setattr(client, "_fetch_by_mmsi", lambda mmsi: details[mmsi])
    return calls


def test_imo_search_filters_non_imo_matches_and_checks_identity(monkeypatch):
    calls = setup_search(monkeypatch, [
        ["UNRELATED", "123456789", "4", "9127136"],
        ["WADI", "622121425", "3", "9127136"],
    ], {"622121425": {"imo": 9127136, "mmsi": 622121425}})
    assert client.fetch_ship_info(imo="9127136", mmsi="622121425")["mmsi"] == 622121425
    assert calls[0]["queryParam"] == "9127136"


def test_without_imo_directly_fetches_mmsi(monkeypatch):
    monkeypatch.setattr(client.requests, "post", lambda *a, **kw: pytest.fail("No search needed"))
    monkeypatch.setattr(client, "_fetch_by_mmsi", lambda mmsi: {"mmsi": mmsi})
    assert client.fetch_ship_info(mmsi="622121425") == {"mmsi": "622121425"}


def test_ambiguous_imo_is_not_selected_arbitrarily(monkeypatch):
    setup_search(monkeypatch, [["A", m, "3", "9127136"] for m in ("622121425", "621094161")],
                 {m: {"imo": "9127136", "mmsi": m} for m in ("622121425", "621094161")})
    with pytest.raises(client.ChinaportsClientError, match="uniquely"):
        client.fetch_ship_info("9127136")


def test_wrong_returned_identity_is_rejected(monkeypatch):
    setup_search(monkeypatch, [["A", "622121425", "3", "9127136"]],
                 {"622121425": {"imo": "9999999", "mmsi": "622121425"}})
    with pytest.raises(client.ChinaportsClientError):
        client.fetch_ship_info(imo="9127136", mmsi="622121425")

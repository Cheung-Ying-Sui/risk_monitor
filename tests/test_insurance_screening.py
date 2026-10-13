from risk_monitor.insurance_screening import screen_shipments


def test_screens_four_parties_once_each_and_preserves_row_evidence():
    calls = []

    def search(name, **kwargs):
        calls.append(name)
        return {"results": [{"profile_id": "123", "source": "OFAC", "matched_name": name,
                             "score": 95}] if name == "Cedant" else []}

    rows = [
        {"extra_data": {"insured_name": "Insured", "shipper": "Shipper", "consignee": "Consignee", "cedant": "Cedant", "source_row": 2}},
        {"extra_data": {"insured_name": "Insured", "shipper": "Shipper", "consignee": "Consignee", "cedant": "Cedant", "source_row": 3}},
    ]
    screened = screen_shipments(rows, None, search=search)
    assert calls == ["Insured", "Shipper", "Consignee", "Cedant"]
    assert [row["extra_data"]["source_row"] for row in screened] == [2, 3]
    assert all(row["extra_data"]["sanctions_screening"]["possible_match_count"] == 1 for row in screened)

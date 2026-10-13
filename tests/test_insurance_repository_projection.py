from risk_monitor.insurance_repository import InsuranceRepository


def test_insured_vessel_projection_excludes_voided_records_and_deduplicates_declarations():
    repository = InsuranceRepository()
    repository.list_policies = lambda **kwargs: [
        {"id": "active", "status": "active"},
        {"id": "void", "status": "cancelled"},
    ]
    repository.list_declarations = lambda **kwargs: [
        {"id": "d0", "policy_id": "active", "status": "pending_review", "declaration_number": "DEC-2026-0000", "company_name": "A", "shipments": [
            {"vessel_name": "Not yet insured", "imo_number": "1111111"},
        ]},
        {"id": "d1", "policy_id": "active", "status": "confirmed", "declaration_number": "DEC-2026-0001", "company_name": "A", "shipments": [
            {"vessel_name": "Wadi Alkarnak", "imo_number": "9127136", "extra_data": {"mmsi_candidate": "622121425", "mmsi_confirmed": True}},
            {"vessel_name": "Wadi Alkarnak", "imo_number": "9127136"},
        ]},
        {"id": "d2", "policy_id": "active", "status": "cancelled", "declaration_number": "DEC-2026-0002", "shipments": [{"vessel_name": "Cancelled", "imo_number": "1234567"}]},
        {"id": "d3", "policy_id": "void", "status": "confirmed", "declaration_number": "DEC-2026-0003", "shipments": [{"vessel_name": "Voided policy", "imo_number": "7654321"}]},
        {"id": "d4", "policy_id": "active", "status": "completed", "declaration_number": "DEC-2026-0004", "shipments": [{"vessel_name": "Past voyage", "imo_number": "7777777"}]},
    ]

    rows = repository.list_insured_vessels()

    assert len(rows) == 1
    assert rows[0]["imo_number"] == "9127136"
    assert rows[0]["declaration_count"] == 1
    assert rows[0]["confirmed_mmsi"] == "622121425"

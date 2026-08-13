from risk_monitor.vessel_repository import upsert_vessel


test_vessel = {
    "mmsi": "413123456",
    "imo": "9876543",
    "ship_name": "TEST VESSEL UPDATED",
    "callsign": "TEST01",
    "length": 200,
    "width": 32,
    "ship_all_dun": 50000,
}


result = upsert_vessel(test_vessel)

print(result)

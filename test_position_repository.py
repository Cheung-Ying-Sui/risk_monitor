from position_repository import upsert_position


test_position = {
    "mmsi": "413123456",
    "latitude": "N 22度19.1580分",
    "longitude": "E 114度10.1640分",
    "trueHeading": "90",
    "cog": "88.2",
    "sog": "12.5",
    "eta": "08-10 12:00",
    "destination": "HONG KONG",
    "draught": "10.5",
    "navStatus": "Under way",
    "timeStamp": "2026-08-08 16:30(UTC+8)",
}


result = upsert_position(test_position)

print(result)

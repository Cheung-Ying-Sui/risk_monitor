from __future__ import annotations


# Lightweight Port Master for ETA MVP.
# This is curated reference data, not a complete global Port Master.
# Coordinates are approximate port/city reference coordinates for baseline ETA.
PORT_MASTER = [
    {
        "unlocode": "SGSIN",
        "port_name": "Singapore",
        "country_code": "SG",
        "country_name": "Singapore",
        "latitude": 1.2644,
        "longitude": 103.8400,
        "aliases": [
            "SINGAPORE",
            "SG SIN",
            "SGSIN",
            "SIN",
        ],
        "source": "UN/LOCODE + public port coordinate reference",
        "source_reference": "UN/LOCODE SGSIN; Singapore port reference coordinates",
    },
    {
        "unlocode": "CNSHA",
        "port_name": "Shanghai",
        "country_code": "CN",
        "country_name": "China",
        "latitude": 31.2304,
        "longitude": 121.4737,
        "aliases": [
            "SHANGHAI",
            "CN SHA",
            "CNSHA",
            "SHA",
        ],
        "source": "UN/LOCODE + public port coordinate reference",
        "source_reference": "UN/LOCODE CNSHA; Shanghai port reference coordinates",
    },
    {
        "unlocode": "HKHKG",
        "port_name": "Hong Kong",
        "country_code": "HK",
        "country_name": "Hong Kong",
        "latitude": 22.3193,
        "longitude": 114.1694,
        "aliases": [
            "HONG KONG",
            "HONGKONG",
            "HK HKG",
            "HKHKG",
            "HKG",
        ],
        "source": "UN/LOCODE + public port coordinate reference",
        "source_reference": "UN/LOCODE HKHKG; Hong Kong port reference coordinates",
    },
    {
        "unlocode": "DEHAM",
        "port_name": "Hamburg",
        "country_code": "DE",
        "country_name": "Germany",
        "latitude": 53.5511,
        "longitude": 9.9937,
        "aliases": [
            "HAMBURG",
            "DE HAM",
            "DEHAM",
        ],
        "source": "UN/LOCODE + public port/city coordinate reference",
        "source_reference": "UN/LOCODE DEHAM; Hamburg reference coordinates",
    },
    {
        "unlocode": "FRLEH",
        "port_name": "Le Havre",
        "country_code": "FR",
        "country_name": "France",
        "latitude": 49.4944,
        "longitude": 0.1079,
        "aliases": [
            "LE HAVRE",
            "LEHAVRE",
            "FR LEH",
            "FRLEH",
        ],
        "source": "UN/LOCODE + public port/city coordinate reference",
        "source_reference": "UN/LOCODE FRLEH; Le Havre reference coordinates",
    },
    {
        "unlocode": "CNLYG",
        "port_name": "Lianyungang",
        "country_code": "CN",
        "country_name": "China",
        "latitude": 34.5967,
        "longitude": 119.2214,
        "aliases": [
            "LIANYUNGANG",
            "LIAN YUN GANG",
            "CN LYG",
            "CNLYG",
            "LYG",
        ],
        "source": "UN/LOCODE + public port/city coordinate reference",
        "source_reference": "UN/LOCODE CNLYG; Lianyungang reference coordinates",
    },
    {
        "unlocode": "MAPTM",
        "port_name": "Tanger Med",
        "country_code": "MA",
        "country_name": "Morocco",
        "latitude": 35.8936,
        "longitude": -5.5014,
        "aliases": [
            "TANGER MED",
            "TANGIER MED",
            "TANGER-MED",
            "MA PTM",
            "MAPTM",
            "PTM",
        ],
        "source": "UN/LOCODE + public port coordinate reference",
        "source_reference": "UN/LOCODE MAPTM; Tanger Med port reference coordinates",
    },
    {
        "unlocode": "CNQDG",
        "port_name": "Qingdao",
        "country_code": "CN",
        "country_name": "China",
        "latitude": 36.0671,
        "longitude": 120.3826,
        "aliases": [
            "QINGDAO",
            "QING DAO",
            "CN QDG",
            "CNQDG",
            "QDG",
            "QINGD",
        ],
        "source": "UN/LOCODE + public port/city coordinate reference",
        "source_reference": "UN/LOCODE CNQDG; Qingdao reference coordinates",
    },
]


def iter_ports():
    return iter(PORT_MASTER)


def find_port_by_unlocode(unlocode):
    normalized_unlocode = str(unlocode or "").strip().upper()
    for port in PORT_MASTER:
        if port["unlocode"] == normalized_unlocode:
            return port
    return None

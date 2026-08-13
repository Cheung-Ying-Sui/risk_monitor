from unittest.mock import patch

from risk_monitor.navigation.destination_normalizer import (
    StaticDestinationLLMResolver,
    clear_destination_cache,
    classify_destination,
    get_port_candidates,
    normalize_destination_text,
    resolve_destination,
)


def test_unlocode_exact():
    clear_destination_cache()
    result = resolve_destination("DEHAM")

    assert result["resolution_status"] == "resolved"
    assert result["unlocode"] == "DEHAM"
    assert result["resolution_method"] == "unlocode_exact"


def test_spacing_normalization():
    result = resolve_destination("cn lyg")

    assert result["resolution_status"] == "resolved"
    assert result["unlocode"] == "CNLYG"


def test_port_name_exact():
    result = resolve_destination("Le Havre")

    assert result["resolution_status"] == "resolved"
    assert result["unlocode"] == "FRLEH"
    assert result["resolution_method"] == "port_name_exact"


def test_alias():
    result = resolve_destination("Tangier Med")

    assert result["resolution_status"] == "resolved"
    assert result["unlocode"] == "MAPTM"
    assert result["resolution_method"] == "alias_exact"


def test_ais_abbreviation_manual_verified():
    result = resolve_destination("QINGD")

    assert result["resolution_status"] == "resolved"
    assert result["unlocode"] == "CNQDG"
    assert result["resolution_method"] == "manual_verified"


def test_ambiguous():
    fake_ports = [
        {
            "unlocode": "AAABC",
            "port_name": "Alpha",
            "country_code": "AA",
            "country_name": "A",
            "latitude": 1,
            "longitude": 1,
            "aliases": ["SAME"],
            "source": "test",
            "source_reference": "test",
        },
        {
            "unlocode": "BBABC",
            "port_name": "Beta",
            "country_code": "BB",
            "country_name": "B",
            "latitude": 2,
            "longitude": 2,
            "aliases": ["SAME"],
            "source": "test",
            "source_reference": "test",
        },
    ]
    with patch(
        "risk_monitor.navigation.destination_normalizer.iter_ports",
        return_value=iter(fake_ports),
    ):
        result = resolve_destination("SAME", use_cache=False)

    assert result["resolution_status"] == "ambiguous"


def test_non_port_text():
    result = resolve_destination("CHINESE OWNERCREW")

    assert result["resolution_status"] == "non_port_destination"
    assert result["resolution_method"] == "non_port_text"


def test_llm_candidate_verified():
    fake_ports = [
        {
            "unlocode": "AAONE",
            "port_name": "Alpha Port",
            "country_code": "AA",
            "country_name": "A",
            "latitude": 1,
            "longitude": 1,
            "aliases": [],
            "source": "test",
            "source_reference": "test",
        },
        {
            "unlocode": "AATWO",
            "port_name": "Alpha Terminal",
            "country_code": "AA",
            "country_name": "A",
            "latitude": 2,
            "longitude": 2,
            "aliases": [],
            "source": "test",
            "source_reference": "test",
        },
    ]
    resolver = StaticDestinationLLMResolver(
        {
            "ALPHA": {
                "is_port_destination": True,
                "candidate_unlocodes": [
                    {
                        "unlocode": "AAONE",
                        "confidence": 0.8,
                    }
                ],
                "ambiguous": False,
                "reason": "candidate match",
            }
        }
    )
    with patch(
        "risk_monitor.navigation.destination_normalizer.get_port_candidates",
        return_value=fake_ports,
    ):
        result = resolve_destination(
            "ALPHA",
            llm_resolver=resolver,
            use_cache=False,
        )

    assert result["resolution_status"] == "resolved"
    assert result["unlocode"] == "AAONE"
    assert result["resolution_method"] == "llm_candidate_verified"


def test_llm_hallucinated_candidate_rejected():
    resolver = StaticDestinationLLMResolver(
        {
            "TANGER": {
                "is_port_destination": True,
                "candidate_unlocodes": [
                    {
                        "unlocode": "ZZFAK",
                        "confidence": 0.99,
                    }
                ],
                "ambiguous": False,
                "reason": "not in candidate set",
            }
        }
    )

    result = resolve_destination(
        "TANGER",
        llm_resolver=resolver,
        use_cache=False,
    )

    assert result["resolution_status"] == "needs_review"
    assert result["resolution_method"] == "llm_candidate_rejected"


def test_cache_hit():
    clear_destination_cache()
    first = resolve_destination("DEHAM")
    second = resolve_destination("DE HAM")

    assert first["cache_hit"] is False
    assert second["cache_hit"] is True


def test_malformed_llm_response():
    resolver = StaticDestinationLLMResolver(
        {
            "TANGER": "not-json",
        }
    )

    result = resolve_destination(
        "TANGER",
        llm_resolver=resolver,
        use_cache=False,
    )

    assert result["resolution_status"] == "needs_review"
    assert result["resolution_method"] == "malformed_llm_response"


def test_normalize_destination_text():
    result = normalize_destination_text(" cn lyg ")

    assert result["normalized_text"] == "CN LYG"
    assert result["compact_text"] == "CNLYG"


def test_get_port_candidates():
    candidates = get_port_candidates("QINGD")

    assert candidates[0]["unlocode"] == "CNQDG"


def test_classify_destination():
    assert classify_destination("DEHAM") == "unlocode_like"
    assert classify_destination("QINGD") == "unlocode_like"
    assert classify_destination("CHINESE OWNERCREW") == "non_port_destination"


if __name__ == "__main__":
    test_unlocode_exact()
    test_spacing_normalization()
    test_port_name_exact()
    test_alias()
    test_ais_abbreviation_manual_verified()
    test_ambiguous()
    test_non_port_text()
    test_llm_candidate_verified()
    test_llm_hallucinated_candidate_rejected()
    test_cache_hit()
    test_malformed_llm_response()
    test_normalize_destination_text()
    test_get_port_candidates()
    test_classify_destination()
    print("test_destination_normalizer.py passed")

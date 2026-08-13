from __future__ import annotations

import json
import re
from copy import deepcopy

from risk_monitor.navigation.port_reference import find_port_by_unlocode, iter_ports


_DESTINATION_CACHE = {}
NON_PORT_TERMS = {
    "CREW",
    "OWNER",
    "OWNERS",
    "CHINESE OWNERCREW",
    "PHASE 2 6 2 VALIDATION",
    "VALIDATION",
}


def normalize_destination_text(raw_destination):
    raw_value = "" if raw_destination is None else str(raw_destination).strip()
    normalized = raw_value.upper()
    normalized = re.sub(r"[^A-Z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    compact = normalized.replace(" ", "")

    return {
        "raw_destination": raw_value,
        "normalized_text": normalized,
        "compact_text": compact,
    }


def classify_destination(raw_destination):
    normalized = normalize_destination_text(raw_destination)
    text = normalized["normalized_text"]
    compact = normalized["compact_text"]

    if not compact:
        return "missing"

    if text in NON_PORT_TERMS or any(term in text for term in ("CREW", "OWNER")):
        return "non_port_destination"

    if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{3}", compact):
        return "unlocode_like"

    if len(compact) <= 6 and compact.isalnum():
        return "port_abbreviation"

    return "free_text"


def _port_tokens(port):
    values = [
        port["unlocode"],
        port["port_name"],
        *port.get("aliases", []),
    ]
    tokens = set()
    for value in values:
        normalized = normalize_destination_text(value)
        if normalized["normalized_text"]:
            tokens.add(normalized["normalized_text"])
        if normalized["compact_text"]:
            tokens.add(normalized["compact_text"])
    return tokens


def _public_port(port):
    return {
        "unlocode": port["unlocode"],
        "port_name": port["port_name"],
        "country_code": port["country_code"],
        "country_name": port["country_name"],
        "latitude": port["latitude"],
        "longitude": port["longitude"],
        "aliases": list(port.get("aliases", [])),
        "source": port["source"],
        "source_reference": port["source_reference"],
    }


def get_port_candidates(raw_destination):
    normalized = normalize_destination_text(raw_destination)
    text = normalized["normalized_text"]
    compact = normalized["compact_text"]
    if not compact:
        return []

    candidates = []
    seen = set()
    for port in iter_ports():
        tokens = _port_tokens(port)
        if text in tokens or compact in tokens:
            candidates.append(_public_port(port))
            seen.add(port["unlocode"])
            continue

        if len(compact) >= 4:
            for token in tokens:
                if len(token) >= 4 and (
                    token.startswith(compact)
                    or compact.startswith(token)
                    or compact in token
                ):
                    if port["unlocode"] not in seen:
                        candidates.append(_public_port(port))
                        seen.add(port["unlocode"])
                    break

    return candidates


class DestinationLLMResolver:
    def resolve(self, raw_destination, normalized_destination, candidate_ports):
        return {
            "is_port_destination": False,
            "candidate_unlocodes": [],
            "ambiguous": False,
            "reason": "llm_resolver_not_configured",
        }


class StaticDestinationLLMResolver(DestinationLLMResolver):
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.call_count = 0

    def resolve(self, raw_destination, normalized_destination, candidate_ports):
        self.call_count += 1
        key = normalized_destination.get("compact_text")
        return self.responses.get(
            key,
            super().resolve(raw_destination, normalized_destination, candidate_ports),
        )


def _parse_llm_response(response):
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except json.JSONDecodeError:
            return None

    if not isinstance(response, dict):
        return None

    candidate_unlocodes = response.get("candidate_unlocodes")
    if not isinstance(candidate_unlocodes, list):
        return None

    return response


def _resolution_base(raw_destination):
    normalized = normalize_destination_text(raw_destination)
    return {
        "raw_destination": normalized["raw_destination"],
        "normalized_input": normalized["normalized_text"],
        "compact_input": normalized["compact_text"],
        "normalized_destination": None,
        "unlocode": None,
        "country_code": None,
        "country_name": None,
        "latitude": None,
        "longitude": None,
        "resolution_status": "unresolved",
        "resolution_method": "unresolved",
        "confidence": "low",
        "candidates": [],
        "source": None,
        "source_reference": None,
        "warnings": [],
    }


def _resolved(raw_destination, port, method, confidence):
    result = _resolution_base(raw_destination)
    result.update(
        {
            "normalized_destination": port["port_name"],
            "unlocode": port["unlocode"],
            "country_code": port["country_code"],
            "country_name": port["country_name"],
            "latitude": port["latitude"],
            "longitude": port["longitude"],
            "resolution_status": "resolved",
            "resolution_method": method,
            "confidence": confidence,
            "source": port["source"],
            "source_reference": port["source_reference"],
        }
    )
    return result


def _cache_key(raw_destination):
    return normalize_destination_text(raw_destination)["compact_text"]


def clear_destination_cache():
    _DESTINATION_CACHE.clear()


def resolve_destination(raw_destination, llm_resolver=None, use_cache=True):
    key = _cache_key(raw_destination)
    if use_cache and key in _DESTINATION_CACHE:
        cached = deepcopy(_DESTINATION_CACHE[key])
        cached["cache_hit"] = True
        return cached

    result = _resolve_destination_uncached(raw_destination, llm_resolver)
    result["cache_hit"] = False
    if use_cache and key:
        _DESTINATION_CACHE[key] = deepcopy(result)
    return result


def _resolve_destination_uncached(raw_destination, llm_resolver=None):
    normalized = normalize_destination_text(raw_destination)
    classification = classify_destination(raw_destination)
    result = _resolution_base(raw_destination)
    result["destination_class"] = classification

    if classification == "missing":
        result["resolution_status"] = "unresolved"
        result["resolution_method"] = "empty_destination"
        result["warnings"].append("destination_missing")
        return result

    if classification == "non_port_destination":
        result["resolution_status"] = "non_port_destination"
        result["resolution_method"] = "non_port_text"
        result["warnings"].append("destination_not_port")
        return result

    if classification == "unlocode_like":
        unlocode = normalized["compact_text"]
        port = find_port_by_unlocode(unlocode)
        if port:
            return _resolved(
                raw_destination,
                _public_port(port),
                "unlocode_exact",
                "high",
            )

    candidates = get_port_candidates(raw_destination)
    result["candidates"] = [
        {
            "unlocode": candidate["unlocode"],
            "port_name": candidate["port_name"],
            "country_code": candidate["country_code"],
        }
        for candidate in candidates
    ]

    exact_matches = [
        candidate
        for candidate in candidates
        if normalized["normalized_text"]
        in {
            normalize_destination_text(candidate["port_name"])["normalized_text"],
            normalize_destination_text(candidate["unlocode"])["normalized_text"],
        }
        or normalized["compact_text"]
        in {
            normalize_destination_text(candidate["port_name"])["compact_text"],
            normalize_destination_text(candidate["unlocode"])["compact_text"],
        }
    ]
    if len(exact_matches) == 1:
        method = "port_name_exact"
        if normalized["compact_text"] == exact_matches[0]["unlocode"]:
            method = "unlocode_exact"
        return _resolved(raw_destination, exact_matches[0], method, "high")
    if len(exact_matches) > 1:
        result["resolution_status"] = "ambiguous"
        result["resolution_method"] = "normalized_exact_ambiguous"
        result["warnings"].append("multiple_exact_candidates")
        return result

    alias_matches = [
        candidate
        for candidate in candidates
        if normalized["normalized_text"]
        in {
            normalize_destination_text(alias)["normalized_text"]
            for alias in candidate.get("aliases", [])
        }
        or normalized["compact_text"]
        in {
            normalize_destination_text(alias)["compact_text"]
            for alias in candidate.get("aliases", [])
        }
    ]
    if len(alias_matches) == 1:
        method = "alias_exact"
        if (
            classification == "port_abbreviation"
            or normalized["compact_text"] != alias_matches[0]["unlocode"]
        ) and len(normalized["compact_text"]) <= 6:
            method = "manual_verified"
        return _resolved(raw_destination, alias_matches[0], method, "high")
    if len(alias_matches) > 1:
        result["resolution_status"] = "ambiguous"
        result["resolution_method"] = "alias_exact_ambiguous"
        result["warnings"].append("multiple_alias_candidates")
        return result

    if len(candidates) > 1 and not llm_resolver:
        result["resolution_status"] = "ambiguous"
        result["resolution_method"] = "candidate_retrieval_ambiguous"
        result["warnings"].append("llm_resolver_required")
        return result

    if llm_resolver and candidates:
        llm_response = _parse_llm_response(
            llm_resolver.resolve(
                raw_destination,
                normalized,
                candidates,
            )
        )
        if llm_response is None:
            result["resolution_status"] = "needs_review"
            result["resolution_method"] = "malformed_llm_response"
            result["warnings"].append("malformed_llm_response")
            return result

        if llm_response.get("ambiguous"):
            result["resolution_status"] = "ambiguous"
            result["resolution_method"] = "llm_candidate_ambiguous"
            result["warnings"].append("llm_marked_ambiguous")
            return result

        candidate_unlocodes = llm_response.get("candidate_unlocodes") or []
        selected = [
            candidate
            for candidate in candidates
            if any(
                str(item.get("unlocode", "")).upper() == candidate["unlocode"]
                for item in candidate_unlocodes
                if isinstance(item, dict)
            )
        ]
        if len(selected) == 1:
            return _resolved(
                raw_destination,
                selected[0],
                "llm_candidate_verified",
                "medium",
            )
        if selected:
            result["resolution_status"] = "ambiguous"
            result["resolution_method"] = "llm_multiple_verified_candidates"
            result["warnings"].append("llm_selected_multiple_candidates")
            return result

        result["resolution_status"] = "needs_review"
        result["resolution_method"] = "llm_candidate_rejected"
        result["warnings"].append("llm_candidate_not_in_port_master_candidates")
        return result

    if llm_resolver and not candidates:
        llm_response = _parse_llm_response(
            llm_resolver.resolve(
                raw_destination,
                normalized,
                [],
            )
        )
        result["resolution_status"] = "needs_review"
        result["resolution_method"] = (
            "llm_suggestion_needs_review"
            if llm_response
            else "malformed_llm_response"
        )
        result["warnings"].append("llm_suggestion_not_auto_resolved")
        return result

    result["resolution_status"] = "unresolved"
    result["resolution_method"] = "port_master_no_match"
    return result

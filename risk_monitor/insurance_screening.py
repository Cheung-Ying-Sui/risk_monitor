"""Screen declaration parties against the configured sanctions data source.

A candidate is not a legal determination. Persist only compact audit evidence,
and do not mark an unavailable screening source as a clear result.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from risk_monitor.sanctions_screening_service import search_sanctions


PARTY_FIELDS = (
    ("insured_name", "被保险人"),
    ("shipper", "托运人"),
    ("consignee", "收货人"),
    ("cedant", "分出公司"),
)


def prepare_shipments_for_screening(
    shipments: list[dict[str, Any]], insured_name: str | None,
) -> list[dict[str, Any]]:
    """Queue submitted parties without claiming that a screening has run.

    Imported/client-provided screening state is never trusted as evidence.
    Drafts are prepared only when the user actually submits them.
    """
    prepared = []
    for shipment in shipments:
        extra = dict(shipment.get("extra_data") or {})
        if not str(extra.get("insured_name") or "").strip() and insured_name:
            extra["insured_name"] = insured_name.strip()
        names = [str(extra.get(field) or "").strip() for field, _ in PARTY_FIELDS]
        if not any(names):
            raise ValueError("请至少填写一个待筛查主体。")
        extra.pop("sanctions_workflow", None)
        extra["sanctions_screening"] = {
            "status": "pending",
            "source": "OFAC SDN",
            "possible_match_count": 0,
            "parties": [],
        }
        prepared.append({**shipment, "extra_data": extra})
    return prepared


def screen_shipments(
    shipments: list[dict[str, Any]],
    insured_name: str | None,
    search: Callable[..., dict[str, Any]] = search_sanctions,
) -> list[dict[str, Any]]:
    cache: dict[str, dict[str, Any]] = {}
    screened = []
    for shipment in shipments:
        extra = dict(shipment.get("extra_data") or {})
        parties = []
        possible_match_count = 0
        for field, label in PARTY_FIELDS:
            name = str(extra.get(field) or (insured_name if field == "insured_name" else "") or "").strip()
            if not name:
                continue
            key = name.casefold()
            if key not in cache:
                result = search(name, min_score=65, limit=5, include_suggestions=False)
                matches = result.get("results") or []
                cache[key] = {
                    "matches": [{"profile_id": item.get("profile_id"), "source": item.get("source"),
                                 "matched_name": item.get("matched_name"), "score": item.get("score")}
                                for item in matches[:5]],
                    "possible_match": bool(matches),
                }
            evidence = cache[key]
            possible_match_count += int(evidence["possible_match"])
            parties.append({"role": field, "label": label, "name": name, **evidence})
        extra["sanctions_screening"] = {
            "status": "completed" if parties else "missing_parties",
            "source": "configured_sanctions_database",
            "screened_at": datetime.now(timezone.utc).isoformat(),
            "possible_match_count": possible_match_count,
            "parties": parties,
        }
        screened.append({**shipment, "extra_data": extra})
    return screened

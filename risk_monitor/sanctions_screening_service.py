import json
import os
import re
import unicodedata

import requests

from risk_monitor.supabase_client import supabase


CORPORATE_SUFFIXES = {"CO", "CORP", "INC", "LIMITED", "LLC", "LTD"}


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKC", str(name or "")).casefold()
    text = re.sub(r"[-.,'\"/()]+", " ", text)
    return " ".join(
        token for token in text.split()
        if token.upper() not in CORPORATE_SUFFIXES
    ).upper()


def _profile(entity_id: str) -> dict | None:
    entity_result = (
        supabase.table("sanctions_entities").select("profile_id,source")
        .eq("id", entity_id).limit(1).execute()
    )
    if not entity_result.data:
        return None

    names = (
        supabase.table("sanctions_names").select("name")
        .eq("entity_id", entity_id).execute().data or []
    )
    addresses = (
        supabase.table("sanctions_addresses").select("address")
        .eq("entity_id", entity_id).execute().data or []
    )
    programs = (
        supabase.table("sanctions_programs").select("program")
        .eq("entity_id", entity_id).execute().data or []
    )
    entity = entity_result.data[0]
    return {
        "profile_id": str(entity.get("profile_id") or entity_id),
        "source": str(entity.get("source") or "OFAC").upper(),
        "names": [item["name"] for item in names if item.get("name")],
        "addresses": [item["address"] for item in addresses if item.get("address")],
        "programs": [item["program"] for item in programs if item.get("program")],
    }


def search_sanctions(
    keyword: str,
    min_score: float = 65,
    limit: int = 50,
    include_suggestions: bool = True,
) -> dict:
    query = str(keyword or "").strip()
    if not query:
        raise ValueError("请输入要筛查的名称。")

    normalized = normalize_name(query)
    matches = (
        supabase.rpc("search_sanctions_names", {
            "query_name": query,
            "normalized_query": normalized,
            "min_similarity": min_score / 100,
            "max_results": limit,
        }).execute().data or []
    )
    suggestions = (
        supabase.rpc("search_sanctions_name_candidates", {
            "normalized_query": normalized,
            "max_results": 10,
        }).execute().data or []
    ) if include_suggestions else []

    results = []
    for match in matches:
        profile = _profile(str(match["entity_id"]))
        if not profile:
            continue
        results.append({
            **profile,
            "matched_name": match.get("name") or "",
            "match_type": match.get("match_type") or "fuzzy",
            "score": float(match.get("score") or 0),
        })

    return {
        "keyword": query,
        "normalized_keyword": normalized,
        "results": results,
        "suggestions": [
            {
                "name": item.get("name") or "",
                "score": float(item.get("candidate_score") or 0),
            }
            for item in suggestions
            if item.get("name")
        ],
    }


def _deepseek_candidates(keyword: str, max_candidates: int = 3) -> list[dict]:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY。")
    prompt = f"""
你是制裁筛查系统中的候选检索词生成器，不负责判断是否制裁命中。
根据用户输入生成可能用于 OFAC SDN 数据库检索的英文法定名、拼音名、常见转写名或完整名称。
只输出 JSON，不要输出 markdown，不要编造制裁结论，最多返回 {max_candidates} 个候选。
输出格式：{{"possible_short_name":true,"candidates":[{{"query":"候选全称","reason":"候选理由","probability":0到100的候选可信度}}]}}
用户输入：{keyword}
"""
    response = requests.post(
        os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/chat/completions"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        json={
            "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            "messages": [
                {"role": "system", "content": "Generate auditable sanctions search candidates. Output strict JSON only."},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        },
        timeout=(5, 25),
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    match = re.search(r"(\{.*\}|\[.*\])", content, re.DOTALL)
    parsed = json.loads(match.group(1) if match else content)
    seen = set()
    candidates = []
    for item in parsed.get("candidates", []):
        query = str(item.get("query") or "").strip()
        if not query or query.casefold() in seen:
            continue
        seen.add(query.casefold())
        try:
            probability = max(0, min(100, float(item.get("probability"))))
        except (TypeError, ValueError):
            probability = None
        candidates.append({"query": query, "reason": str(item.get("reason") or ""), "ai_probability": probability})
    return candidates[:max_candidates]


def search_with_ai_candidates(keyword: str, min_score: float = 65) -> list[dict]:
    generated = _deepseek_candidates(keyword)
    assisted = []
    for candidate in generated:
        try:
            search_result = search_sanctions(
                candidate["query"], min_score=min_score, limit=5,
                include_suggestions=False,
            )
            best_match = search_result["results"][0] if search_result["results"] else None
            best_suggestion = search_result["suggestions"][0] if search_result["suggestions"] else None
        except Exception:
            best_match = None
            best_suggestion = None
        assisted.append({
            **candidate,
            "matched_name": best_match["matched_name"] if best_match else (best_suggestion["name"] if best_suggestion else None),
            "match_score": best_match["score"] if best_match else (best_suggestion["score"] if best_suggestion else None),
            "profile_id": best_match["profile_id"] if best_match else None,
            "programs": best_match["programs"] if best_match else [],
            "formal_match": best_match is not None,
        })
    return assisted

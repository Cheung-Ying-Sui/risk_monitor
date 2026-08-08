import json
import os
import re
from pathlib import Path

import requests

from search import search_entity

try:
    from dotenv import load_dotenv
    load_dotenv(
        Path(__file__).resolve().parent / ".env",
        override=True
    )
except ImportError:
    pass


DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv(
    "DEEPSEEK_BASE_URL",
    "https://api.deepseek.com/chat/completions"
)
DEEPSEEK_MODEL = os.getenv(
    "DEEPSEEK_MODEL",
    "deepseek-chat"
)


def clean_json_string(raw_text):
    match = re.search(
        r"(\{.*\}|\[.*\])",
        raw_text,
        re.DOTALL
    )

    if match:
        return match.group(1)

    return raw_text


def call_deepseek_for_candidates(keyword, max_candidates=8):
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("Missing DEEPSEEK_API_KEY environment variable.")

    prompt = f"""
你是制裁筛查系统中的候选检索词生成器，不负责判断是否制裁命中。

任务：
根据用户输入的企业、个人、船舶或组织名称，生成可能用于 OFAC SDN 数据库检索的候选英文名、拼音名、常见转写名或更完整名称。

要求：
1. 只输出 JSON，不要输出 markdown。
2. 不要判断该主体是否被制裁。
3. 不要编造制裁结论。
4. 候选词应尽量短而可检索，例如英文法定名、拼音转写、核心英文 token。
5. 如果输入是中文企业名，可以生成拼音/英文行业词组合。
6. 最多返回 {max_candidates} 个候选。

输出格式：
{{
  "input": "...",
  "input_type": "company|person|vessel|unknown",
  "possible_short_name": true,
  "candidates": [
    {{
      "query": "candidate search name",
      "reason": "why this candidate may be relevant"
    }}
  ]
}}

用户输入：
{keyword}
"""

    response = requests.post(
        DEEPSEEK_BASE_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
        },
        json={
            "model": DEEPSEEK_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "You generate auditable search candidates for sanctions screening. Output strict JSON only."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "response_format": {
                "type": "json_object"
            }
        },
        timeout=60
    )
    response.raise_for_status()

    content = response.json()["choices"][0]["message"]["content"]
    return json.loads(
        clean_json_string(content)
    )


def dedupe_candidates(candidates):
    seen = set()
    deduped = []

    for candidate in candidates:
        query = str(
            candidate.get("query", "")
        ).strip()

        if not query:
            continue

        key = query.casefold()

        if key in seen:
            continue

        seen.add(key)
        deduped.append(
            {
                "query": query,
                "reason": candidate.get("reason", "")
            }
        )

    return deduped


def search_ai_candidates(
    keyword,
    min_score=65,
    search_limit=5,
    ai_candidate_limit=8
):
    ai_response = call_deepseek_for_candidates(
        keyword,
        max_candidates=ai_candidate_limit
    )

    generated_candidates = dedupe_candidates(
        ai_response.get("candidates", [])
    )[:ai_candidate_limit]

    results = []

    for candidate in generated_candidates:
        search_result = search_entity(
            candidate["query"],
            min_score=min_score,
            limit=search_limit,
            candidate_limit=search_limit
        )

        formal_results = search_result.get(
            "results",
            []
        )

        short_name_candidates = search_result.get(
            "candidate_full_names",
            []
        )

        if not formal_results and not short_name_candidates:
            continue

        results.append(
            {
                "generated_query": candidate["query"],
                "reason": candidate["reason"],
                "requires_full_name_confirmation": True,
                "formal_results": formal_results,
                "candidate_full_names": short_name_candidates
            }
        )

    return {
        "input": keyword,
        "input_type": ai_response.get("input_type", "unknown"),
        "possible_short_name": ai_response.get("possible_short_name"),
        "generated_candidates": generated_candidates,
        "ai_assisted_candidates": results,
        "message": "AI 仅生成候选检索词；候选结果不等同于正式制裁命中，请确认完整法定名称后重新筛查。"
    }


if __name__ == "__main__":
    print(
        json.dumps(
            search_ai_candidates(
                "舟山耀海航运有限公司"
            ),
            ensure_ascii=False,
            indent=2
        )
    )

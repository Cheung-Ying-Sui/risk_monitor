from supabase_client import supabase
from normalizer import normalize_name


def classify_risk(score):
    if score >= 95:
        return {
            "risk_level": "high_confidence",
            "review_required": False,
            "decision": "match"
        }

    if score >= 80:
        return {
            "risk_level": "medium_confidence",
            "review_required": True,
            "decision": "review"
        }

    return {
        "risk_level": "low_confidence",
        "review_required": True,
        "decision": "weak_match"
    }


def fetch_entity_profile(entity_id):
    entity_result = (
        supabase
        .table("sanctions_entities")
        .select("*")
        .eq(
            "id",
            entity_id
        )
        .execute()
    )

    if not entity_result.data:
        return None

    entity = entity_result.data[0]

    address_result = (
        supabase
        .table("sanctions_addresses")
        .select("address")
        .eq(
            "entity_id",
            entity_id
        )
        .execute()
    )

    program_result = (
        supabase
        .table("sanctions_programs")
        .select("program")
        .eq(
            "entity_id",
            entity_id
        )
        .execute()
    )

    names_result = (
        supabase
        .table("sanctions_names")
        .select("name,normalized_name")
        .eq(
            "entity_id",
            entity_id
        )
        .execute()
    )

    return {
        "profile_id": entity["profile_id"],
        "source": entity["source"],
        "names": [
            item["name"]
            for item in names_result.data
        ],
        "normalized_names": [
            item["normalized_name"]
            for item in names_result.data
        ],
        "addresses": [
            item["address"]
            for item in address_result.data
        ],
        "programs": [
            item["program"]
            for item in program_result.data
        ]
    }


def search_name_records(
    keyword,
    min_score=65,
    limit=50
):
    normalized_keyword = normalize_name(
        keyword
    )

    result = (
        supabase
        .rpc(
            "search_sanctions_names",
            {
                "query_name": keyword,
                "normalized_query": normalized_keyword,
                "min_similarity": min_score / 100,
                "max_results": limit
            }
        )
        .execute()
    )

    return normalized_keyword, list(
        result.data
    )


def search_short_name_candidates(
    normalized_keyword,
    limit=10
):
    result = (
        supabase
        .rpc(
            "search_sanctions_name_candidates",
            {
                "normalized_query": normalized_keyword,
                "max_results": limit
            }
        )
        .execute()
    )

    return [
        {
            "name": record["name"],
            "normalized_name": record["normalized_name"],
            "match_type": record["match_type"],
            "candidate_score": record["candidate_score"],
            "requires_full_name_confirmation": record["requires_full_name_confirmation"],
            "message": "检测到你可能使用了简称。请确认交易对手的完整法定名称后重新筛查。"
        }
        for record in result.data
    ]


def search_entity(
    keyword,
    min_score=65,
    limit=50,
    candidate_limit=10
):
    normalized_keyword, name_records = search_name_records(
        keyword,
        min_score=min_score,
        limit=limit
    )

    candidate_full_names = search_short_name_candidates(
        normalized_keyword,
        limit=candidate_limit
    )

    if not name_records:
        return {
            "hit": False,
            "keyword": keyword,
            "normalized_keyword": normalized_keyword,
            "candidate_detected": bool(candidate_full_names),
            "candidate_full_names": candidate_full_names,
            "message": (
                "检测到你可能使用了简称。数据库中存在可能的完整名称候选；"
                "请确认完整法定名称后重新筛查。"
                if candidate_full_names
                else "未发现正式命中或简称候选。"
            )
        }

    results = []

    for name_record in name_records:
        profile = fetch_entity_profile(
            name_record["entity_id"]
        )

        if profile is None:
            continue

        profile.update(
            {
                "matched_name": name_record["name"],
                "matched_normalized_name": name_record["normalized_name"],
                "match_type": name_record["match_type"],
                "score": name_record["score"],
                **classify_risk(
                    name_record["score"]
                )
            }
        )

        results.append(
            profile
        )

    return {
        "hit": bool(results),
        "keyword": keyword,
        "normalized_keyword": normalized_keyword,
        "min_score": min_score,
        "results": results,
        "candidate_detected": bool(candidate_full_names),
        "candidate_full_names": candidate_full_names
    }


if __name__ == "__main__":
    result = search_entity(
        "恒力石化大连有限公司"
    )

    print(result)

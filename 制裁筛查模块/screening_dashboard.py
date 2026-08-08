import json

import pandas as pd
import streamlit as st

from ai_candidate_search import search_ai_candidates
from search import search_entity
from supabase_client import supabase


st.set_page_config(
    page_title="OFAC SDN Screening",
    layout="wide"
)

st.markdown(
    """
    <style>
        .main .block-container {
            max-width: 1280px;
            padding-top: 24px;
        }
        [data-testid="stMetricValue"] {
            font-size: 22px;
        }
        .status-box {
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            padding: 14px 16px;
            background: #F8FAFC;
        }
    </style>
    """,
    unsafe_allow_html=True
)


def format_list(values):
    if not values:
        return ""
    return "; ".join(str(value) for value in values)


def build_results_table(results):
    rows = []

    for item in results:
        rows.append(
            {
                "Score": item.get("score"),
                "Risk": item.get("risk_level"),
                "Decision": item.get("decision"),
                "Review": item.get("review_required"),
                "Match Type": item.get("match_type"),
                "Matched Name": item.get("matched_name"),
                "Profile ID": item.get("profile_id"),
                "Programs": format_list(item.get("programs")),
                "Addresses": format_list(item.get("addresses")),
            }
        )

    return pd.DataFrame(rows)


def build_candidates_table(candidates):
    rows = []

    for item in candidates:
        rows.append(
            {
                "Candidate Score": item.get("candidate_score"),
                "Candidate Full Name": item.get("name"),
                "Normalized Name": item.get("normalized_name"),
                "Match Type": item.get("match_type"),
                "Requires Confirmation": item.get("requires_full_name_confirmation"),
            }
        )

    return pd.DataFrame(rows)


def build_ai_candidates_table(ai_result):
    rows = []

    for item in ai_result.get("ai_assisted_candidates", []):
        for formal_result in item.get("formal_results", []):
            rows.append(
                {
                    "Generated Query": item.get("generated_query"),
                    "Reason": item.get("reason"),
                    "Score": formal_result.get("score"),
                    "Match Type": formal_result.get("match_type"),
                    "Matched Name": formal_result.get("matched_name"),
                    "Profile ID": formal_result.get("profile_id"),
                    "Decision": formal_result.get("decision"),
                    "Requires Confirmation": item.get("requires_full_name_confirmation"),
                }
            )

        for candidate in item.get("candidate_full_names", []):
            rows.append(
                {
                    "Generated Query": item.get("generated_query"),
                    "Reason": item.get("reason"),
                    "Score": candidate.get("candidate_score"),
                    "Match Type": candidate.get("match_type"),
                    "Matched Name": candidate.get("name"),
                    "Profile ID": "",
                    "Decision": "confirm_full_name",
                    "Requires Confirmation": candidate.get("requires_full_name_confirmation"),
                }
            )

    return pd.DataFrame(rows)


def fetch_latest_import_batch():
    result = (
        supabase
        .table("sanctions_import_batches")
        .select(
            "started_at,completed_at,status,total_entries,success_count,"
            "failed_count,inserted_count,reactivated_count,inactive_count,"
            "file_hash"
        )
        .order(
            "started_at",
            desc=True
        )
        .limit(
            1
        )
        .execute()
    )

    if not result.data:
        return None

    return result.data[0]


def fetch_entity_status_counts():
    active_result = (
        supabase
        .table("sanctions_entities")
        .select(
            "id",
            count="exact"
        )
        .eq(
            "source",
            "OFAC"
        )
        .eq(
            "is_active",
            True
        )
        .limit(
            1
        )
        .execute()
    )
    inactive_result = (
        supabase
        .table("sanctions_entities")
        .select(
            "id",
            count="exact"
        )
        .eq(
            "source",
            "OFAC"
        )
        .eq(
            "is_active",
            False
        )
        .limit(
            1
        )
        .execute()
    )

    return {
        "active": active_result.count or 0,
        "inactive": inactive_result.count or 0
    }


def render_data_status():
    try:
        latest_batch = fetch_latest_import_batch()
        status_counts = fetch_entity_status_counts()
    except Exception as exc:
        st.warning(
            f"无法读取 OFAC 数据同步状态：{exc}"
        )
        return

    if not latest_batch:
        st.warning("尚未发现 OFAC 数据同步批次。")
        return

    completed_at = latest_batch.get(
        "completed_at"
    ) or "未完成"
    status = latest_batch.get(
        "status",
        "unknown"
    )
    failed_count = latest_batch.get(
        "failed_count",
        0
    )

    st.caption(
        f"OFAC 数据状态：最新同步完成时间 {completed_at} | "
        f"状态 {status} | 失败 {failed_count}"
    )

    status_cols = st.columns(5)
    status_cols[0].metric(
        "同步记录",
        latest_batch.get(
            "total_entries",
            0
        )
    )
    status_cols[1].metric(
        "成功处理",
        latest_batch.get(
            "success_count",
            0
        )
    )
    status_cols[2].metric(
        "新增主体",
        latest_batch.get(
            "inserted_count",
            0
        )
    )
    status_cols[3].metric(
        "当前有效",
        status_counts["active"]
    )
    status_cols[4].metric(
        "已移除",
        status_counts["inactive"]
    )


st.title("OFAC SDN 制裁筛查测试台")
render_data_status()

with st.sidebar:
    st.header("筛查参数")
    min_score = st.slider(
        "模糊匹配最低分",
        min_value=50,
        max_value=95,
        value=65,
        step=5
    )
    limit = st.number_input(
        "正式命中返回数量",
        min_value=1,
        max_value=100,
        value=20,
        step=1
    )
    candidate_limit = st.number_input(
        "简称候选返回数量",
        min_value=1,
        max_value=50,
        value=10,
        step=1
    )
    enable_ai_candidates = st.checkbox(
        "启用 AI 辅助候选",
        value=False
    )
    ai_candidate_limit = st.number_input(
        "AI 候选检索词数量",
        min_value=1,
        max_value=12,
        value=8,
        step=1,
        disabled=not enable_ai_candidates
    )

query = st.text_input(
    "输入公司、个人、船舶或别名",
    value="恒力石化",
    placeholder="例如：AEROCARIBBEAN AIRLINE / 恒力石化"
)

col_search, col_clear = st.columns([1, 5])
with col_search:
    submitted = st.button(
        "筛查",
        type="primary",
        use_container_width=True
    )
with col_clear:
    st.empty()

if submitted:
    cleaned_query = query.strip()

    if not cleaned_query:
        st.warning("请输入要筛查的名称。")
        st.stop()

    with st.spinner("正在查询 OFAC SDN 数据库..."):
        result = search_entity(
            cleaned_query,
            min_score=min_score,
            limit=int(limit),
            candidate_limit=int(candidate_limit)
        )

    if enable_ai_candidates:
        with st.spinner("正在生成 AI 辅助候选并二次检索数据库..."):
            result["ai_candidate_result"] = search_ai_candidates(
                cleaned_query,
                min_score=min_score,
                search_limit=5,
                ai_candidate_limit=int(ai_candidate_limit)
            )

    st.session_state["last_result"] = result

result = st.session_state.get("last_result")

if not result:
    st.info("输入名称后点击筛查。简称会作为候选提示，不会直接判定为正式命中。")
    st.stop()

results = result.get("results", [])
candidates = result.get("candidate_full_names", [])
ai_candidate_result = result.get("ai_candidate_result")

metric_cols = st.columns(4)
metric_cols[0].metric(
    "正式命中",
    "是" if result.get("hit") else "否"
)
metric_cols[1].metric(
    "正式结果数",
    len(results)
)
metric_cols[2].metric(
    "简称候选",
    len(candidates)
)
metric_cols[3].metric(
    "标准化输入",
    result.get("normalized_keyword", "")
)

if result.get("message"):
    st.warning(result["message"])

if results:
    st.subheader("正式筛查结果")
    st.dataframe(
        build_results_table(results),
        use_container_width=True,
        hide_index=True
    )

    for index, item in enumerate(results, start=1):
        title = f"{index}. {item.get('matched_name')} | {item.get('score')} | {item.get('decision')}"
        with st.expander(title):
            detail_cols = st.columns(2)
            with detail_cols[0]:
                st.write("Profile ID:", item.get("profile_id"))
                st.write("Source:", item.get("source"))
                st.write("Match Type:", item.get("match_type"))
                st.write("Risk Level:", item.get("risk_level"))
                st.write("Review Required:", item.get("review_required"))
            with detail_cols[1]:
                st.write("Programs:", format_list(item.get("programs")))
                st.write("Addresses:", format_list(item.get("addresses")))

            st.write("All Names")
            st.dataframe(
                pd.DataFrame(
                    {
                        "name": item.get("names", []),
                        "normalized_name": item.get("normalized_names", [])
                    }
                ),
                use_container_width=True,
                hide_index=True
    )

if ai_candidate_result:
    st.subheader("AI 辅助候选")
    st.info(
        ai_candidate_result.get(
            "message",
            "AI 候选结果不等同于正式制裁命中。"
        )
    )

    generated_candidates = ai_candidate_result.get(
        "generated_candidates",
        []
    )

    if generated_candidates:
        st.write("AI 生成的候选检索词")
        st.dataframe(
            pd.DataFrame(generated_candidates),
            use_container_width=True,
            hide_index=True
        )

    ai_table = build_ai_candidates_table(
        ai_candidate_result
    )

    if not ai_table.empty:
        st.write("数据库二次检索候选")
        st.dataframe(
            ai_table,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.caption("AI 生成的候选检索词未召回数据库候选。")

if candidates:
    st.subheader("简称候选")
    st.dataframe(
        build_candidates_table(candidates),
        use_container_width=True,
        hide_index=True
    )
    st.caption(
        "简称候选不是正式制裁命中。请确认交易对手完整法定名称后重新筛查。"
    )

with st.expander("原始 JSON"):
    st.code(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2
        ),
        language="json"
    )

import streamlit as st
from streamlit_autorefresh import st_autorefresh
import json
import os

# 导入自定义功能模块
# 需要正确导入 risk_zones 模块中的脚本
from risk_zones import risk_zones_LLM_get_data as risk_zones_llm, map_manager

# --- 1. 页面配置 ---
st.set_page_config(page_title="Sinochem Risk Monitor", layout="wide", initial_sidebar_state="collapsed")

# 资源路径
VIDEO_URL = "static/shipping_video.mp4"
LAND_MASK_URL = "static/land_mask.json"
PROCESSED_ZONE_FILE = "../risk_zones/processed_risk_zones.json"

# --- 2. 注入静默更新逻辑 ---
@st.cache_resource(ttl=86400)
def init_data_sync():
    # 调用 LLM 脚本来自动抓取和更新风险区域数据
    # 为了避免每次启动都耗时请求 AI，这里应该加上判断，只有文件不存在或过期才更新
    if not os.path.exists(PROCESSED_ZONE_FILE):
         risk_zones_llm.auto_update_zones()
    return True
init_data_sync()

def get_active_risk_zones():
    """从本地 JSON 文件读取最新的处理后风险数据"""
    if os.path.exists(PROCESSED_ZONE_FILE):
        with open(PROCESSED_ZONE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"countries": [], "zones": []}

# --- 3. 页面布局：Banner ---
st.markdown(f"""
    <div style="position: relative; width: 100%; height: 400px; overflow: hidden; background-color: #002855;">
        <video autoplay loop muted playsinline style="position: absolute; top: 50%; left: 50%; min-width: 100%; min-height: 100%; transform: translate(-50%, -50%); object-fit: cover;">
            <source src="{VIDEO_URL}" type="video/mp4">
        </video>
        <div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0, 40, 85, 0.55); display: flex; flex-direction: column; align-items: center; justify-content: center; color: white;">
            <h1 style='font-size: 3rem; font-weight: 700; letter-spacing: 4px;'>MARINE RISK MONITORING</h1>
            <p style='font-size: 1.2rem; opacity: 0.9;'>中化保险经纪 - 全球航运风险平台</p>
        </div>
    </div>
""", unsafe_allow_html=True)

# --- 4. 数据加载 ---
risk_data = get_active_risk_zones()
risk_countries = risk_data.get("countries", [])
risk_zones_list = risk_data.get("zones", [])

# --- 5. 交互筛选器 ---
st.markdown('<div style="padding: 20px 60px; background-color: #f8f9fa;">', unsafe_allow_html=True)
c1, c2, c3 = st.columns([1, 2, 1])
with c2:
    country_opts = {"ALL": "显示所有区域 (Global Overview)"}
    for c in risk_countries:
        country_opts[c.get("iso_code")] = f"{c.get('name')} ({c.get('iso_code')})"
    selected_iso = st.selectbox("区域风险聚焦", options=list(country_opts.keys()), format_func=lambda x: country_opts[x])
st.markdown('</div>', unsafe_allow_html=True)

# --- 6. 数据看板 Metrics ---
st.markdown("<br><div style='padding: 0 60px;'>", unsafe_allow_html=True)
c1, c2 = st.columns(2)
c1.metric("HIGH RISK COUNTRIES", len(risk_countries))
c2.metric("MARITIME RISK ZONES", len(risk_zones_list))
st.markdown("</div>", unsafe_allow_html=True)

# --- 7. 地图渲染 ---
# 调用 map_manager 的聚合函数，直接获取配置好的地图对象
deck = map_manager.generate_risk_map_deck(risk_zones_list, risk_countries, LAND_MASK_URL)

st.pydeck_chart(deck, use_container_width=True)

st_autorefresh(interval=10000, key="global_refresh")
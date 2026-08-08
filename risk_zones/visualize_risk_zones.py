import streamlit as st
import pydeck as pdk
from risk_zones import risk_zones_LLM_get_data
import os
import json

# 页面配置
st.set_page_config(page_title="Risk Zones Debugger", layout="wide")
st.title("JWC Risk Zones Visualization Debugger")

# --- 自动执行更新 (Auto Update) ---
# 页面加载时自动触发更新，确保 risk_maritime.geojson 被生成
if "has_auto_updated" not in st.session_state:
    with st.spinner("正在自动执行数据更新与几何裁切..."):
        success, msg = risk_zones_data_get.auto_update_zones()
        if success:
            st.success(f"自动更新成功: {msg}")
        else:
            st.error(f"自动更新失败: {msg}")
    st.session_state["has_auto_updated"] = True
    st.rerun()

# --- 侧边栏：控制面板 ---
with st.sidebar:
    st.header("Actions")
    st.info("点击下方按钮可强制触发 '爬虫 -> DeepSeek解析 -> 几何裁切' 的全流程。")
    
    if st.button("Run Auto Update"):
        with st.spinner("正在调用 DeepSeek API 及执行空间运算..."):
            success, msg = risk_zones_LLM_get_data.auto_update_zones()
            if success:
                st.success(f"更新成功! {msg}")
                st.rerun()
            else:
                st.error(f"更新失败: {msg}")
    
    st.divider()
    st.markdown("**说明：**\n此工具用于验证 `risk_zones_LLM_get_data.py` 的输出结果。\n红色区域即为 AI 识别并经海岸线裁切后的风险范围。")

# --- 数据加载 ---
data = risk_zones_data_get.get_active_risk_zones()

# 显示当前数据源
source_file = risk_zones_data_get.PROCESSED_ZONE_FILE if os.path.exists(risk_zones_data_get.PROCESSED_ZONE_FILE) else risk_zones_data_get.RISK_ZONE_FILE
st.sidebar.caption(f"📂 Data Source: `{source_file}`")

zones = data.get("zones", [])
countries = data.get("countries", [])

# --- 顶部指标 ---
c1, c2 = st.columns(2)
c1.metric("Risk Zones (Polygons)", len(zones))
c2.metric("Risk Countries (ISO)", len(countries))

# --- 主体内容：地图与数据 ---
tab1, tab2 = st.tabs(["🗺️ Map Visualization", "📄 Raw JSON Data"])

with tab1:
    layers = []
    
    # 1. 风险海域层：优先读取 GeoJSON 文件 (包含海岸线裁切结果)
    risk_maritime_file = getattr(risk_zones_data_get, "RISK_MARITIME_GEOJSON", "risk_maritime.geojson")
    if os.path.exists(risk_maritime_file):
        with open(risk_maritime_file, "r") as f:
            maritime_geo = json.load(f)
            
        layers.append(pdk.Layer(
            "GeoJsonLayer",
            data=maritime_geo,
            get_fill_color=[255, 75, 75, 100],  # 红色半透明
            get_line_color=[255, 255, 255, 200], # 白色边框
            get_line_width=2,
            pickable=True,
            auto_highlight=True,
            stroked=True,
            filled=True,
            wrap_longitude=True
        ))
    elif zones:
        # 降级方案：如果 GeoJSON 不存在，使用原始数据
        layers.append(pdk.Layer(
            "PolygonLayer",
            data=zones,
            get_polygon="polygon",
            get_fill_color=[255, 75, 75, 100],
            get_line_color=[255, 255, 255, 200],
            get_line_width=2,
            pickable=True,
            filled=True
        ))

    # 集成 risk_geography 可视化高风险国家
    if countries:
        # 使用包含国家边界和 ISO 代码的公开 GeoJSON 源
        COUNTRIES_URL = "https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json"
        country_geo = risk_geography.get_risk_country_geojson(COUNTRIES_URL, countries)
        
        if country_geo.get("features"):
            layers.append(pdk.Layer(
                "GeoJsonLayer",
                data=country_geo,
                get_fill_color=[255, 75, 75, 100],  # 与海域颜色保持一致
                get_line_color=[255, 255, 255, 200],
                get_line_width=1,
                pickable=True,
                auto_highlight=True,
                wrap_longitude=True,  # 关键修复：解决俄罗斯等跨越 180 度经线国家的渲染问题
                stroked=True,
                filled=True
            ))

    if layers:
        view_state = pdk.ViewState(
            latitude=25.0,
            longitude=55.0,
            zoom=2,
            pitch=0
        )

        # 渲染地图
        st.pydeck_chart(pdk.Deck(
            map_style='https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json',
            initial_view_state=view_state,
            layers=layers,
            tooltip={"html": "<b>{name}</b><br/>{description}"}
        ))
    else:
        st.warning("暂无风险区域数据。请点击侧边栏的 'Run Auto Update' 按钮生成数据。")

with tab2:
    st.subheader("Current Data Content")
    st.json(data)
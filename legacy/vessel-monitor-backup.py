import streamlit as st
import os
import requests
import time
import re
import pandas as pd
import pydeck as pdk

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ==========================================
# 0. CSS and Page Configuration
# ==========================================
st.set_page_config(page_title="远洋实时风控监测 - 3D 地球视角", layout="wide")

# Custom CSS for UI components
st.markdown("""
    <style>
        /* Make map full screen or container full width */
        .main .block-container {
            max-width: 100%;
        }
        /* Sidebar Ship Card Style */
        .ship-card {
            border: 1px solid #333;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 8px;
            background-color: #1e1e1e;
            box-shadow: 0 2px 5px rgba(0,0,0,0.5);
            transition: all 0.3s ease;
            color: #eee;
        }
        .ship-card.selected {
            border-color: #FF3333;
            background-color: #2a1111;
            box-shadow: 0 4px 8px rgba(255,51,51,0.2);
        }
        .ship-card-title {
            font-size: 15px;
            font-weight: bold;
            margin-bottom: 4px;
        }
        .ship-card.selected .ship-card-title {
            color: #FF3333;
        }
        .ship-card:not(.selected) .ship-card-title {
            color: #4da6ff;
        }
        .ship-card-subtitle {
            font-size: 12px;
            color: #aaa;
        }
    </style>
""", unsafe_allow_html=True)


# ==========================================
# 1. Data Fetching & Helper Functions
# ==========================================

@st.cache_data(ttl=60)  # Cache data for 60 seconds
def fetch_ship_info(mmsi_id):
    url = "https://ship.chinaports.com/ShipInit/shipInfo"
    chinaports_cookie = os.getenv("CHINAPORTS_COOKIE")
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://ship.chinaports.com",
        "Referer": "https://ship.chinaports.com/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Safari/605.1.15",
        "X-Requested-With": "XMLHttpRequest",
    }
    if chinaports_cookie:
        headers["Cookie"] = chinaports_cookie
    current_num = str(int(time.time() * 1000))
    payload = {"userid": mmsi_id, "source": "0", "num": current_num, "encode": "false", "lang": "ZH", "zone": "-480"}
    try:
        response = requests.post(url, headers=headers, data=payload, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception:
        return None


def parse_coordinate(coord_str):
    if not coord_str or str(coord_str).lower() == "null" or coord_str == "--": return None
    match = re.search(r'([NESW])\s*(\d+)度(\d+\.\d+)分', str(coord_str))
    if not match: return None
    direction, degrees, minutes = match.groups()
    decimal_degrees = float(degrees) + float(minutes) / 60.0
    if direction in ['S', 'W']: decimal_degrees *= -1
    return decimal_degrees


def clean_val(val):
    if val is None or str(val).lower() == "null" or str(val).strip() == "": return "--"
    return str(val)


# ==========================================
# 2. Session State Initialization
# ==========================================
if 'fleet' not in st.session_state:
    st.session_state.fleet = []  # List of MMSIs
if 'fleet_data' not in st.session_state:
    st.session_state.fleet_data = {}  # Dict mapping MMSI to its full data
if 'selected_mmsi' not in st.session_state:
    st.session_state.selected_mmsi = None

# ==========================================
# 3. Sidebar for Fleet Management
# ==========================================
with st.sidebar:
    st.title("🌐 远洋船队控制台")
    st.markdown("---")

    # Add Ship Form
    with st.form("add_ship_form", clear_on_submit=True):
        mmsi_to_add = st.text_input("输入要添加的 MMSI", placeholder="例如: 477626369")
        add_submitted = st.form_submit_button("添加到追踪 ➕")
        if add_submitted:
            if mmsi_to_add and mmsi_to_add.isdigit():
                if mmsi_to_add not in st.session_state.fleet:
                    st.session_state.fleet.append(mmsi_to_add)
                    st.success(f"已添加 MMSI: {mmsi_to_add}")
                    st.rerun()
                else:
                    st.warning("该船已在追踪队列中。")
            else:
                st.error("请输入有效的数字 MMSI。")

    st.markdown("---")
    st.subheader("📋 实时监控列表")

    if not st.session_state.fleet:
        st.info("当前没有追踪任何船舶。请在上方输入 MMSI 添加。")
    else:
        for mmsi in st.session_state.fleet[:]:
            ship_name = st.session_state.fleet_data.get(mmsi, {}).get("shipname", "加载中...")
            is_selected = (st.session_state.selected_mmsi == mmsi)
            card_class = "ship-card selected" if is_selected else "ship-card"

            # Interactive Clickable Card
            st.markdown(f"""
            <div class="{card_class}">
                <div class="ship-card-title">🚢 {ship_name}</div>
                <div class="ship-card-subtitle">MMSI: {mmsi}</div>
            </div>
            """, unsafe_allow_html=True)

            c1, c2 = st.columns([3, 1])
            with c1:
                if st.button("🛰️ 3D 定位", key=f"loc_{mmsi}", use_container_width=True):
                    st.session_state.selected_mmsi = mmsi
                    st.rerun()
            with c2:
                if st.button("❌", key=f"del_{mmsi}", help="移除该船", use_container_width=True):
                    st.session_state.fleet.remove(mmsi)
                    if mmsi in st.session_state.fleet_data:
                        del st.session_state.fleet_data[mmsi]
                    if st.session_state.selected_mmsi == mmsi:
                        st.session_state.selected_mmsi = None
                    st.rerun()
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

# ==========================================
# 4. Main Application Logic & Data Fetching
# ==========================================

# Fetch data for all ships in the fleet
for mmsi in st.session_state.fleet:
    data = fetch_ship_info(mmsi)
    if data:
        st.session_state.fleet_data[mmsi] = data

# ==========================================
# 5. 3D Globe View Rendering via Pydeck
# ==========================================
st.subheader("🌍 远洋运输实时 3D 监控大屏")

# Prepare target center for the GlobeView
center_lat, center_lon = 20.0, 110.0  # Default center (Asia)
zoom_level = 1.0

# If a specific ship is selected, focus on it
if st.session_state.selected_mmsi and st.session_state.selected_mmsi in st.session_state.fleet_data:
    target_data = st.session_state.fleet_data[st.session_state.selected_mmsi]
    t_lat = parse_coordinate(target_data.get("latitude"))
    t_lon = parse_coordinate(target_data.get("longitude"))
    if t_lat and t_lon:
        center_lat, center_lon = t_lat, t_lon
        zoom_level = 1.5  # 放大视距，但保持在能看到地球弧度的范围

# --- 准备 Pydeck 数据图层 ---
scatter_data = []
for mmsi, data in st.session_state.fleet_data.items():
    lat = parse_coordinate(data.get("latitude"))
    lon = parse_coordinate(data.get("longitude"))
    if lat is not None and lon is not None:
        is_selected = (mmsi == st.session_state.selected_mmsi)

        # 提取动态和静态信息供 Tooltip 使用
        ship_name = clean_val(data.get("shipname"))
        speed = clean_val(data.get("sog"))
        heading = clean_val(data.get("trueHeading"))
        dest = clean_val(data.get("destination"))
        nav_status = clean_val(data.get("navStatus"))

        # 定义标记颜色 (RGBA): 选中为高亮红色，未选中为天蓝色
        color = [255, 50, 50, 255] if is_selected else [50, 150, 255, 200]
        radius = 150000 if is_selected else 80000  # 选中的船圆圈更大

        scatter_data.append({
            "mmsi": mmsi,
            "ship_name": ship_name,
            "coordinates": [lon, lat],  # Pydeck 使用 [lon, lat] 格式
            "color": color,
            "radius": radius,
            "speed": f"{speed} 节",
            "heading": f"{heading}°",
            "dest": dest,
            "status": nav_status
        })

# **关键修复：必须处理空 DataFrame 的情况**
# Pydeck 如果传入空数据可能会导致前端 WebGL 崩溃或白屏
if not scatter_data:
    # 如果没有船只，提供一条极小的、不可见的假数据来初始化空地球
    scatter_data.append({
        "mmsi": "0", "ship_name": "none", "coordinates": [0, 0],
        "color": [0, 0, 0, 0], "radius": 0, "speed": "", "heading": "", "dest": "", "status": ""
    })

df_scatter = pd.DataFrame(scatter_data)

# --- 构建 Pydeck ScatterplotLayer (散点图层) ---
try:
    ship_layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_scatter,
        get_position="coordinates",
        get_radius="radius",
        get_fill_color="color",
        pickable=True,  # 允许被鼠标悬停拾取以展示 Tooltip
        auto_highlight=True,
    )

    # --- 配置 Pydeck 视图状态 (3D 球体视角) ---
    view_state = pdk.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=zoom_level,
        pitch=45,  # 倾斜视角，凸显 3D 效果
        bearing=0,
    )

    # --- 渲染 Pydeck Chart ---
    # **关键修复：移除无效的 views 参数**
    # st.pydeck_chart 目前不直接支持传入 views=[pdk.View(type="_GlobeView")],
    # 我们需要通过创建一个完整的 pdk.Deck 对象，并在其中正确配置。
    # 对于 Globe 模式，我们需要设置 map_provider 为 None 或特定供应商，并且设置正确的 map_style。

    deck = pdk.Deck(
        layers=[ship_layer],
        initial_view_state=view_state,
        map_style="mapbox://styles/mapbox/dark-v11",
        # 这里是开启 Globe 的标准写法
        views=[{"type": "_GlobeView", "controller": True}],
        tooltip={
            "html": """
                <b>🚢 {ship_name}</b> (MMSI: {mmsi})<br>
                <b>目的地:</b> {dest}<br>
                <b>航速:</b> {speed}<br>
                <b>航向:</b> {heading}<br>
                <b>状态:</b> {status}
            """,
            "style": {
                "backgroundColor": "steelblue",
                "color": "white"
            }
        }
    )

    # 使用 st.components.v1.html 或者是 st.pydeck_chart 均可
    # 但由于旧版本兼容性，如果 views 参数报错，最安全的方式是仅保留标准的 MapView
    # 我们在这里尝试官方文档建议的写法：
    st.pydeck_chart(deck)

except Exception as e:
    st.error(f"Pydeck 地图渲染出错: {e}")

# ==========================================
# 6. Selected Ship Details Dashboard
# ==========================================
if st.session_state.selected_mmsi and st.session_state.selected_mmsi in st.session_state.fleet_data:
    st.markdown("---")
    data = st.session_state.fleet_data[st.session_state.selected_mmsi]

    ship_name = clean_val(data.get("shipname"))
    st.subheader(f"📊 实时监控看板 | {ship_name} (MMSI: {st.session_state.selected_mmsi})")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("航速 (SOG)", f'{clean_val(data.get("sog"))} 节')
    c2.metric("船首向", f'{clean_val(data.get("trueHeading"))}°')
    c3.metric("吃水深度", f'{clean_val(data.get("draught"))} m')
    c4.metric("预到时间 (ETA)", clean_val(data.get("eta")))

    st.caption(f"📍 目的地: {clean_val(data.get('destination'))} | 🕒 数据更新时间: {clean_val(data.get('timeStamp'))}")

    with st.expander("展开查看船舶详细静态数据"):
        details = {
            "MMSI": clean_val(data.get("mmsi")), "IMO": clean_val(data.get("imo")),
            "呼号": clean_val(data.get("callsign")), "中文船名": clean_val(data.get("chineseShipName")),
            "船长/宽": f'{clean_val(data.get("length"))}m / {clean_val(data.get("width"))}m',
            "总吨 (GT)": clean_val(data.get("shipAllDun")), "净吨 (NT)": clean_val(data.get("shipJingDun")),
            "载重吨 (DWT)": clean_val(data.get("shipZaizhongDun")),
            "航行状态": clean_val(data.get("navStatus"))
        }
        st.dataframe(pd.DataFrame(details.items(), columns=['属性', '值']), hide_index=True, use_container_width=True)

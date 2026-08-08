import streamlit as st
import os
import requests
import time
import re
import pandas as pd
from streamlit_folium import st_folium
import folium

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ==========================================
# 0. CSS and Page Configuration
# ==========================================
st.set_page_config(page_title="船舶实时监控", layout="wide")

# Custom CSS for full-screen map and Sidebar Cards
st.markdown("""
    <style>
        /* Make map full screen */
        .main .block-container {
            padding: 0;
            margin: 0;
            max-width: 100%;
        }
        /* Sidebar Ship Card Style */
        .ship-card {
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 8px;
            background-color: #ffffff;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
            transition: all 0.3s ease;
        }
        .ship-card.selected {
            border-color: #FF3333;
            background-color: #FFF0F0;
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
            color: #0066CC;
        }
        .ship-card-subtitle {
            font-size: 12px;
            color: #666;
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
if 'map_center' not in st.session_state:
    st.session_state.map_center = [22.0, 114.0]
if 'map_zoom' not in st.session_state:
    st.session_state.map_zoom = 5

# ==========================================
# 3. Sidebar for Fleet Management
# ==========================================
with st.sidebar:
    st.title("🚢 船队控制台")
    st.markdown("---")

    # Add Ship Form
    with st.form("add_ship_form", clear_on_submit=True):
        mmsi_to_add = st.text_input("输入要添加的 MMSI", placeholder="例如: 477626369")
        add_submitted = st.form_submit_button("添加到船队 ➕")
        if add_submitted:
            if mmsi_to_add and mmsi_to_add.isdigit():
                if mmsi_to_add not in st.session_state.fleet:
                    st.session_state.fleet.append(mmsi_to_add)
                    st.success(f"已添加 MMSI: {mmsi_to_add}")
                    st.rerun()
                else:
                    st.warning("该船已在船队中。")
            else:
                st.error("请输入有效的数字 MMSI。")

    st.markdown("---")
    st.subheader("📋 当前追踪列表")

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
                # Clicking this button triggers the map animation to the ship
                if st.button("📍 定位船舶", key=f"loc_{mmsi}", use_container_width=True):
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
# 5. Full-Screen Map Rendering & Animation
# ==========================================

old_center = st.session_state.map_center
old_zoom = st.session_state.map_zoom
new_center = old_center
new_zoom = old_zoom

# Calculate new center and zoom if a ship is selected
if st.session_state.selected_mmsi and st.session_state.selected_mmsi in st.session_state.fleet_data:
    data = st.session_state.fleet_data[st.session_state.selected_mmsi]
    lat = parse_coordinate(data.get("latitude"))
    lon = parse_coordinate(data.get("longitude"))
    if lat and lon:
        new_center = [lat, lon]
        new_zoom = 11  # Scale approx 50km
elif st.session_state.fleet_data:
    coords = []
    for data in st.session_state.fleet_data.values():
        lat = parse_coordinate(data.get("latitude"))
        lon = parse_coordinate(data.get("longitude"))
        if lat and lon: coords.append([lat, lon])
    if coords:
        df_coords = pd.DataFrame(coords)
        new_center = [df_coords[0].mean(), df_coords[1].mean()]
        new_zoom = 5

# Always initialize Folium Map at the OLD center to preserve visual continuity before animation
m = folium.Map(location=old_center, zoom_start=old_zoom, tiles="OpenStreetMap", control_scale=True)

# Inject transition animation (flyTo) if the center or zoom needs to change
if old_center != new_center or old_zoom != new_zoom:
    map_id = m.get_name()
    # Adding javascript into the html property of the map root
    flyto_js = f"""
    <script>
        function executeFlyTo() {{
            var mapObj = window['{map_id}'];
            if (mapObj && typeof mapObj.flyTo === 'function') {{
                mapObj.flyTo({new_center}, {new_zoom}, {{
                    duration: 2.5,          // 动画持续 2.5 秒
                    easeLinearity: 0.25     // 飞行曲线平滑度
                }});
            }} else {{
                // 如果地图对象还未就绪，200ms 后重试
                setTimeout(executeFlyTo, 200);
            }}
        }}
        // 开始轮询，直到寻找到地图对象并执行动画
        setTimeout(executeFlyTo, 200);
    </script>
    """
    m.get_root().html.add_child(folium.Element(flyto_js))
    # Save the new state
    st.session_state.map_center = new_center
    st.session_state.map_zoom = new_zoom

# Add OpenSeaMap overlay layer
folium.TileLayer(
    tiles='https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png',
    attr='<a href="https://www.openseamap.org">OpenSeaMap</a> contributors',
    name='航海专属图层 (OpenSeaMap)',
    overlay=True,
    control=True,
    opacity=1.0
).add_to(m)

# Add Ships to Map
for mmsi, data in st.session_state.fleet_data.items():
    lat = parse_coordinate(data.get("latitude"))
    lon = parse_coordinate(data.get("longitude"))

    if lat and lon:
        ship_name = clean_val(data.get("shipname"))
        heading = clean_val(data.get("trueHeading", data.get("cog", 0)))
        try:
            rotation = float(heading)
        except (ValueError, TypeError):
            rotation = 0

        # Color coding: Red if selected, Blue otherwise
        is_selected = (mmsi == st.session_state.selected_mmsi)
        icon_color = "#FF3333" if is_selected else "#0066CC"
        scale = 1.3 if is_selected else 1.0

        svg_icon_html = f"""
        <div style="transform: rotate({rotation}deg) scale({scale}); transform-origin: center; transition: all 0.3s;">
            <svg width="24" height="30" viewBox="0 0 24 30" xmlns="http://www.w3.org/2000/svg" style="filter: drop-shadow(0px 2px 4px rgba(0,0,0,0.5));">
                <path d="M12 0 L24 24 L12 20 L0 24 Z" fill="{icon_color}" stroke="white" stroke-width="1.5" />
            </svg>
        </div>"""

        # Comprehensive Tooltip replacing the old floating panel
        tooltip_html = f"""
        <div style="min-width: 240px; font-family: sans-serif; font-size: 13px;">
            <div style="font-size: 15px; font-weight: bold; color: {icon_color}; border-bottom: 1px solid #ccc; padding-bottom: 5px; margin-bottom: 8px;">
                🚢 {ship_name}
            </div>
            <b>MMSI:</b> {mmsi}<br>
            <b>目的地:</b> {clean_val(data.get("destination"))}<br>
            <b>航速:</b> {clean_val(data.get("sog"))} 节<br>
            <b>对地航向 (COG):</b> {clean_val(data.get("cog"))}°<br>
            <b>船首向 (Heading):</b> {heading}°<br>
            <b>吃水:</b> {clean_val(data.get("draught"))} m<br>
            <b>预到时间:</b> {clean_val(data.get("eta"))}<br>
            <hr style="margin: 8px 0; border: 0; border-top: 1px dashed #eee;">
            <b>呼号:</b> {clean_val(data.get("callsign"))}<br>
            <b>IMO:</b> {clean_val(data.get("imo"))}<br>
            <b>船长/宽:</b> {clean_val(data.get("length"))}m / {clean_val(data.get("width"))}m<br>
            <b>总吨:</b> {clean_val(data.get("shipAllDun"))}<br>
            <b>航行状态:</b> {clean_val(data.get("navStatus"))}<br>
            <div style="margin-top: 8px; font-size: 11px; color: #999; text-align: right;">
                更新于: {clean_val(data.get("timeStamp"))}
            </div>
        </div>
        """

        popup_content = f"<b>{ship_name}</b><br>MMSI: {mmsi}"

        folium.Marker(
            [lat, lon],
            popup=popup_content,
            tooltip=folium.Tooltip(tooltip_html),
            icon=folium.DivIcon(html=svg_icon_html, icon_size=(30, 30), icon_anchor=(15, 15))
        ).add_to(m)

# Add LayerControl
folium.LayerControl().add_to(m)

# Render map spanning the full container width
map_data = st_folium(m, use_container_width=True, height=850, returned_objects=['last_object_clicked_popup'])

# Handle map clicks (Sync map clicks with sidebar selection)
if map_data and map_data.get('last_object_clicked_popup'):
    popup_text = map_data['last_object_clicked_popup']
    clicked_mmsi_match = re.search(r'MMSI: (\d+)', popup_text)
    if clicked_mmsi_match:
        clicked_mmsi = clicked_mmsi_match.group(1)
        if st.session_state.selected_mmsi != clicked_mmsi:
            st.session_state.selected_mmsi = clicked_mmsi
            st.rerun()

import streamlit as st
import streamlit.components.v1 as components
import requests
import time
import re
import json
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 导入我们已经写好的入库模块
import sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "获取船舶地理位置【已开发完成】"))
try:
    from loading_to_postgresql import upsert_vessel_static_data, upsert_vessel_dynamic_data
except ImportError:
    st.error("无法加载数据库写入模块，请检查路径。")
    upsert_vessel_static_data = None
    upsert_vessel_dynamic_data = None

# ==========================================
# 0. 页面配置与暗黑/现代风格 CSS
# ==========================================
st.set_page_config(page_title="船舶实时监控 | MapLibre", layout="wide")

st.markdown("""
    <style>
        /* 隐藏 Streamlit 默认的 padding，实现全屏地图 */
        .main .block-container {
            padding: 0 !important;
            margin: 0 !important;
            max-width: 100% !important;
        }

        /* 亮色调的侧边栏卡片风格 */
        [data-testid="stSidebar"] {
            background-color: #F8FAFC; /* 极浅的蓝灰背景 */
            color: #0F172A; /* 深色文字 */
        }
        .ship-card {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 10px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            transition: all 0.2s ease;
        }
        .ship-card:hover {
            border-color: #0EA5E9;
            box-shadow: 0 4px 6px rgba(14, 165, 233, 0.2);
        }
        .ship-card-title {
            font-size: 16px;
            font-weight: 600;
            color: #0F172A;
            margin-bottom: 4px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .ship-card-subtitle {
            font-size: 12px;
            color: #64748B;
        }
    </style>
""", unsafe_allow_html=True)


# ==========================================
# 1. 数据获取逻辑 (保留你的原始请求机制)
# ==========================================
@st.cache_data(ttl=60)
def fetch_ship_info(mmsi_id):
    url = "https://ship.chinaports.com/ShipInit/shipInfo"
    chinaports_cookie = os.getenv("CHINAPORTS_COOKIE")
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
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
# 2. 状态初始化
# ==========================================
if 'fleet' not in st.session_state:
    st.session_state.fleet = ["477626369"]  # 给个默认的演示 MMSI
if 'fleet_data' not in st.session_state:
    st.session_state.fleet_data = {}
if 'fly_to_target' not in st.session_state:
    st.session_state.fly_to_target = None  # 用于触发镜头动画

# ==========================================
# 3. 左侧导航栏 - 仿 OpenGridWorks 风格
# ==========================================
with st.sidebar:
    st.markdown("<h2 style='color:#F8FAFC;'> 船队控制台</h2>", unsafe_allow_html=True)

    # --- 1. 添加追踪表单 ---
    with st.form("add_ship_form", clear_on_submit=True):
        mmsi_to_add = st.text_input("MMSI 号码", placeholder="例如: 477626369")
        if st.form_submit_button("添加追踪 ➕", use_container_width=True):
            if mmsi_to_add and mmsi_to_add.isdigit() and mmsi_to_add not in st.session_state.fleet:
                st.session_state.fleet.append(mmsi_to_add)
                
                # 获取数据并只写入静态表
                new_ship_data = fetch_ship_info(mmsi_to_add)
                if new_ship_data and upsert_vessel_static_data:
                    # 仅把获取到的数据写入 static 静态表中
                    success = upsert_vessel_static_data(new_ship_data)
                    if success:
                        st.toast(f"已获取 {mmsi_to_add} 基本信息并写入静态库！", icon="✅")
                    else:
                        st.toast(f"获取 {mmsi_to_add} 基本信息失败或入库异常", icon="❌")
                
                st.rerun()

    st.markdown("---")

    # --- 2. 新增：风险区域图层控制 ---
    st.markdown("###  图层控制")
    show_risk_zones = st.checkbox("JWC Listed Areas（3rd March 2026）", value=False)

    st.markdown("---")

    # --- 3. 船队列表展示 ---
    for mmsi in st.session_state.fleet[:]:
        data = fetch_ship_info(mmsi)
        if data:
            st.session_state.fleet_data[mmsi] = data
            ship_name = clean_val(data.get("shipname"))
            sog = clean_val(data.get("sog"))
            lat = parse_coordinate(data.get("latitude"))
            lon = parse_coordinate(data.get("longitude"))

            # 渲染卡片
            st.markdown(f"""
            <div class="ship-card">
                <div class="ship-card-title"><span style="font-size: 20px;">📍</span> {ship_name}</div>
                <div class="ship-card-subtitle">MMSI: {mmsi} &nbsp;|&nbsp; 航速: {sog} 节</div>
            </div>
            """, unsafe_allow_html=True)

            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                if st.button("锁定视角", key=f"loc_{mmsi}", use_container_width=True):
                    if lat and lon:
                        st.session_state.fly_to_target = [lon, lat]  # MapLibre 是 [经度, 纬度]
            with c2:
                # 确认【最终船舶动态信息】按钮，仅更新 dynamic 动态表
                if st.button("最终更新入库", key=f"sync_{mmsi}", use_container_width=True):
                    if upsert_vessel_dynamic_data:
                         success = upsert_vessel_dynamic_data(data)
                         if success:
                             st.toast(f"✅ MMSI: {mmsi} 动态轨迹已更新至 PostgreSQL", icon="💾")
                         else:
                             st.toast(f"❌ MMSI: {mmsi} 动态更新失败", icon="🚨")
            with c3:
                if st.button("❌", key=f"del_{mmsi}", use_container_width=True):
                    st.session_state.fleet.remove(mmsi)
                    del st.session_state.fleet_data[mmsi]
                    st.rerun()

# ==========================================
# 4. 构建 MapLibre 所需的 GeoJSON 数据
# ==========================================
features = []
# 确保 session_state 里有 selected_mmsi，用于判断变色
selected_mmsi = st.session_state.get('selected_mmsi', None)

for mmsi, data in st.session_state.fleet_data.items():
    lat = parse_coordinate(data.get("latitude"))
    lon = parse_coordinate(data.get("longitude"))
    if lat and lon:
        heading = data.get("trueHeading", data.get("cog", 0))
        try:
            heading = float(heading)
        except (ValueError, TypeError):
            heading = 0

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]
            },
            "properties": {
                "mmsi": mmsi,
                "name": clean_val(data.get("shipname")),
                "heading": heading,
                "cog": clean_val(data.get("cog")),
                "sog": clean_val(data.get("sog")),
                "eta": clean_val(data.get("eta")),
                "navStatus": clean_val(data.get("navStatus")),
                "destination": clean_val(data.get("destination")),
                "draught": clean_val(data.get("draught")),
                "callsign": clean_val(data.get("callsign")),
                "imo": clean_val(data.get("imo")),
                "length": clean_val(data.get("length")),
                "width": clean_val(data.get("width")),
                "shipAllDun": clean_val(data.get("shipAllDun")),
                "timeStamp": clean_val(data.get("timeStamp"))
            }
        })

geojson_data = {
    "type": "FeatureCollection",
    "features": features
}

# 处理飞行动画逻辑
initial_center = [114.0, 22.0]
initial_zoom = 5
fly_to_script = ""

if st.session_state.get('fly_to_target'):
    target_lon, target_lat = st.session_state.fly_to_target
    fly_to_script = f"""
        map.flyTo({{
            center: [{target_lon}, {target_lat}],
            zoom: 12,
            speed: 1.5,
            curve: 1.2
        }});
    """
    st.session_state.fly_to_target = None


risk_geojson_str = "null"

if show_risk_zones:
    risk_file_path = "JWLA_033/JWLA_033_Risk_Seas_Merge_Layer.json"
    if os.path.exists(risk_file_path):
        with open(risk_file_path, "r", encoding="utf-8") as f:
            risk_geojson_str = f.read()


# ==========================================
# 5. 生成并注入 MapLibre HTML/JS (亮色版底图)
# ==========================================
maplibre_html = f"""
<!DOCTYPE html>
<html>
<head>
    <script src="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.js"></script>
    <link href="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css" rel="stylesheet" />
    <style>
        body {{ margin: 0; padding: 0; background: #F8FAFC; }}
        #map {{ position: absolute; top: 0; bottom: 0; width: 100%; }}

        /* 亮色风格的弹窗 */
        .maplibregl-popup-content {{
            background: rgba(255, 255, 255, 0.95) !important;
            backdrop-filter: blur(8px);
            color: #0F172A !important;
            border: 1px solid #E2E8F0;
            border-radius: 8px !important;
            padding: 14px !important;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }}
        .maplibregl-popup-anchor-bottom .maplibregl-popup-tip {{
            border-top-color: rgba(255, 255, 255, 0.95) !important;
        }}
        .maplibregl-popup-close-button {{
            color: #64748B;
            font-size: 16px;
        }}
        .maplibregl-popup-close-button:hover {{
            background-color: transparent;
            color: #0F172A;
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    <script>
        const map = new maplibregl.Map({{
            container: 'map',
            style: 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',
            center: {initial_center},
            zoom: {initial_zoom}
        }});

        map.on('load', () => {{

            // 注入并渲染风险区域图层
            const riskZonesData = {risk_geojson_str};

            if (riskZonesData !== null) {{
                map.addSource('risk-zones', {{
                    'type': 'geojson',
                    'data': riskZonesData
                }});

                // 添加多边形填充图层 (半透明红色)
                map.addLayer({{
                    'id': 'risk-zones-fill',
                    'type': 'fill',
                    'source': 'risk-zones',
                    'layout': {{}},
                    'paint': {{
                        'fill-color': '#FF4B4B',
                        'fill-opacity': 0.4
                    }}
                }});

                // 添加多边形边框图层 (白色边框)
                map.addLayer({{
                    'id': 'risk-zones-line',
                    'type': 'line',
                    'source': 'risk-zones',
                    'layout': {{}},
                    'paint': {{
                        'line-color': '#FFFFFF',
                        'line-width': 2,
                        'line-opacity': 0.8
                    }}
                }});
            }}

            const geojsonData = {json.dumps(geojson_data)};
            const selectedMmsi = "{selected_mmsi or ''}";

            // 1. 添加 OpenSeaMap 航海图层
            map.addSource('openseamap', {{
                'type': 'raster',
                'tiles': [
                    'https://tiles.openseamap.org/seamark/{{z}}/{{x}}/{{y}}.png'
                ],
                'tileSize': 256,
                'attribution': '<a href="https://www.openseamap.org">OpenSeaMap</a> contributors'
            }});

            map.addLayer({{
                'id': 'openseamap-layer',
                'type': 'raster',
                'source': 'openseamap',
                'paint': {{
                    'raster-opacity': 1.0
                }}
            }});

            // 2. 遍历每一艘船，为其创建自定义的 HTML Marker
            geojsonData.features.forEach(feature => {{
                const props = feature.properties;
                const coords = feature.geometry.coordinates;

                const isSelected = (props.mmsi === selectedMmsi);
                const iconColor = isSelected ? "#EF4444" : "#0EA5E9"; 
                const scale = isSelected ? 1.3 : 1.0;

                const el = document.createElement('div');
                el.style.cursor = 'pointer';
                el.innerHTML = `
                    <div style="transform: rotate(${{props.heading}}deg) scale(${{scale}}); transform-origin: center; transition: all 0.3s;">
                        <svg width="24" height="30" viewBox="0 0 24 30" xmlns="http://www.w3.org/2000/svg" style="filter: drop-shadow(0px 2px 4px rgba(0,0,0,0.3));">
                            <path d="M12 0 L24 24 L12 20 L0 24 Z" fill="${{iconColor}}" stroke="white" stroke-width="1.5" />
                        </svg>
                    </div>
                `;

                const popupHtml = `
                    <div style="min-width: 180px; max-width: 350px; height: auto; max-height: 350px; overflow-y: auto; font-family: sans-serif; font-size: 13px; line-height: 1.6;">
                        <div style="font-size: 15px; font-weight: bold; color: ${{iconColor}}; border-bottom: 1px solid #E2E8F0; padding-bottom: 5px; margin-bottom: 8px;">
                            🚢 ${{props.name}}
                        </div>
                        <b>MMSI:</b> ${{props.mmsi}}<br>
                        <b>目的地:</b> ${{props.destination}}<br>
                        <b>航速:</b> ${{props.sog}} 节<br>
                        <b>对地航向 (COG):</b> ${{props.cog}}°<br>
                        <b>船首向 (Heading):</b> ${{props.heading}}°<br>
                        <b>吃水:</b> ${{props.draught}} m<br>
                        <b>预到时间:</b> ${{props.eta}}<br>
                        <hr style="margin: 8px 0; border: 0; border-top: 1px dashed #E2E8F0;">
                        <b>呼号:</b> ${{props.callsign}}<br>
                        <b>IMO:</b> ${{props.imo}}<br>
                        <b>船长/宽:</b> ${{props.length}}m / ${{props.width}}m<br>
                        <b>总吨:</b> ${{props.shipAllDun}}<br>
                        <b>航行状态:</b> ${{props.navStatus}}<br>
                        <div style="margin-top: 8px; font-size: 11px; color: #94A3B8; text-align: right;">
                            更新于: ${{props.timeStamp}}
                        </div>
                    </div>
                `;

                const popup = new maplibregl.Popup({{ offset: 15, closeButton: true }})
                    .setHTML(popupHtml);

                new maplibregl.Marker({{ element: el }})
                    .setLngLat(coords)
                    .setPopup(popup)
                    .addTo(map);
            }});

            {fly_to_script}
        }});
    </script>
</body>
</html>
"""

# 将 HTML 注入到 Streamlit
components.html(maplibre_html, height=850, scrolling=False)

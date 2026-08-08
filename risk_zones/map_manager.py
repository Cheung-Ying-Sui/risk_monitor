import pydeck as pdk
import json
import os


def create_maritime_layer(risk_zones: list):
    """
    底层：海域多边形层 (优先使用 GeoJSON)
    """
    maritime_file = "risk_maritime.geojson"
    
    if os.path.exists(maritime_file):
        try:
            with open(maritime_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return pdk.Layer(
                "GeoJsonLayer",
                data=data,
                get_fill_color=[255, 75, 75, 100],
                get_line_color=[255, 255, 255, 200],
                get_line_width=2,
                pickable=True,
                auto_highlight=True,
                stroked=True,
                filled=True,
                wrap_longitude=True
            )
        except Exception:
            pass

    # 降级回退
    return pdk.Layer(
        "PolygonLayer",
        data=risk_zones,
        get_polygon="polygon",
        get_fill_color=[255, 75, 75, 100],
        get_line_color=[255, 255, 255, 200],
        get_line_width=2,
        pickable=True,
        filled=True
    )

def create_land_mask_layer(land_mask_url: str):
    """
    中层：全量陆地遮罩层
    用于显示非风险区域的陆地背景
    """
    try:
        with open(land_mask_url, 'r', encoding='utf-8') as f:
            land_data = json.load(f)
    except Exception:
        land_data = []

    return pdk.Layer(
        "GeoJsonLayer",
        data=land_data,
        stroked=True,
        filled=True,
        get_fill_color=[60, 60, 60, 255],  # 深灰色陆地，与深色底图协调
        get_line_color=[100, 100, 100, 255],
        get_line_width=1,
    )

def create_risk_country_layer(land_mask_url: str, risk_countries: list):
    """
    上层：风险国家高亮层
    优先加载预生成的 GeoJSON 文件，如果不存在则实时生成
    """
    risk_country_file = "risk_countries.geojson"
    
    try:
        # 策略：优先读取 risk_zones_LLM_get_data.py 生成的缓存文件，确保与海域数据版本一致
        if os.path.exists(risk_country_file):
            with open(risk_country_file, 'r', encoding='utf-8') as f:
                filtered_data = json.load(f)
        else:
            # 如果缓存不存在，调用 risk_geography 实时生成
            filtered_data = risk_geography.get_risk_country_geojson(land_mask_url, risk_countries)
            
    except Exception as e:
        print(f"Error creating risk country layer: {e}")
        filtered_data = {"type": "FeatureCollection", "features": []}

    return pdk.Layer(
        "GeoJsonLayer",
        filtered_data,
        get_fill_color=[255, 75, 75, 100],  # 保持与海域颜色一致
        get_line_color=[255, 255, 255, 50],
        get_line_width=1,
        stroked=True,
        filled=True,
        wrap_longitude=True,  # 修复跨越日界线的渲染
        pickable=True,
    )

def generate_risk_map_deck(risk_zones: list, risk_countries: list, land_mask_url: str) -> pdk.Deck:
    """
    核心聚合函数：负责图层叠加与地图对象生成
    图层顺序（从下到上）：海域风险区 -> 陆地遮罩 -> 风险国家高亮
    """
    layers = [
        create_maritime_layer(risk_zones),
        create_land_mask_layer(land_mask_url),
        create_risk_country_layer(land_mask_url, risk_countries)
    ]

    # 初始视角同步自 visualize_risk_zones.py
    view_state = pdk.ViewState(
        latitude=25.0,
        longitude=55.0,
        zoom=2,
        pitch=0
    )

    return pdk.Deck(
        # 切换为 CartoDB Dark Matter 风格
        # 这种风格对比度更高，且底图干扰元素更少，非常适合展示风险热力图
        map_style='https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json',
        initial_view_state=view_state,
        layers=layers,
        tooltip={"html": "<b>{name}</b><br/>{description}"}
    )
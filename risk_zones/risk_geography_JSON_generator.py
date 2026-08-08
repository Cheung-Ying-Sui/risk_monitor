import json
import os
import requests
from shapely.geometry import Polygon, MultiPolygon, shape, mapping
from shapely.ops import unary_union
import geopandas as gpd

# 移除对 Indian Ocean 的全局硬编码屏蔽，因为我们将使用交集来裁剪它
EXCLUDED_WATER_BODIES = []

def load_geojson_as_geodataframe(path: str, crs="EPSG:4326") -> gpd.GeoDataFrame:
    """辅助函数：安全地加载 GeoJSON 为 GeoDataFrame"""
    if os.path.exists(path):
        try:
            return gpd.read_file(path).to_crs(crs)
        except Exception as e:
            print(f"  [警告] 无法加载文件 {path}：{e}")
    return gpd.GeoDataFrame(geometry=[], crs=crs)

def create_risk_maritime_geojson(llm_zones: list, iho_seas_path: str, land_mask_path: str, output_path: str) -> list:
    """
    接收 LLM 提取的区域数据，匹配本地 IHO 数据库，
    并执行交集（限制范围）与差集（排除 12 海里领海）操作。
    """
    iho_features_by_id = {}
    iho_features_by_name = {}

    print("\n--- [GIS 装配日志: 空间运算引擎启动] ---")
    
    # --- 1. 加载底层 IHO 数据 ---
    if os.path.exists(iho_seas_path):
        with open(iho_seas_path, 'r', encoding='utf-8') as f:
            iho_data = json.load(f)
            for feature in iho_data.get('features', []):
                props = feature.get('properties', {})
                name = props.get('name', props.get('NAME', props.get('Name', ''))).strip()

                raw_id = props.get('iho_id', props.get('id', props.get('ID', props.get('IHO_ID'))))
                if not raw_id:
                    raw_id = feature.get('id')

                iho_id = str(raw_id).strip() if raw_id is not None else ""
                geom = shape(feature['geometry'])

                if iho_id:
                    iho_features_by_id[iho_id] = geom
                if name:
                    iho_features_by_name[name.lower()] = geom
        print(f"  [+] 成功加载本地 IHO 数据库：已建立名称和 ID 索引。")

    # --- 2. 预加载并准备 12 海里海岸线缓冲区 ---
    # 1 海里 = 1852 米，12 海里 = 22224 米。
    # 我们使用投影坐标系 (例如 EPSG:3857，墨卡托) 以米为单位计算缓冲区，然后再转回 EPSG:4326
    print(f"  [+] 正在加载陆地边界以计算 12 海里领海缓冲区...")
    coastline_gdf = load_geojson_as_geodataframe(land_mask_path)
    
    coastline_12nm_buffer = None
    if not coastline_gdf.empty:
        try:
            # 转为以米为单位的投影系 (伪墨卡托)
            coastline_proj = coastline_gdf.to_crs("EPSG:3857")
            # 缓冲 22224 米 (12 nm)
            coastline_buffer_proj = coastline_proj.geometry.buffer(22224)
            # 转回经纬度
            coastline_buffer_4326 = coastline_buffer_proj.to_crs("EPSG:4326")
            coastline_12nm_buffer = coastline_buffer_4326.unary_union
            print(f"  [+] 12 海里领海缓冲区预计算完成。")
        except Exception as e:
            print(f"  [警告] 12 海里缓冲区计算失败：{e}")

    final_processed_zones = []
    maritime_features = []

    # --- 3. 处理每个 LLM 解析出的区域 ---
    for zone in llm_zones:
        zone_name = zone.get("zone_name", "Unnamed Zone")
        print(f"\n📁 正在处理区域: {zone_name}")

        components = zone.get("components", {})
        
        # 3.1 获取该区域涉及的基础水体
        base_water_geoms = []
        successful_bodies = []
        named_bodies = components.get("named_water_bodies", [])
        
        for body in named_bodies:
            body_name = body.get("name", "").strip()
            body_id = str(body.get("iho_id", "")).strip()
            search_name = body_name.lower()

            if search_name in EXCLUDED_WATER_BODIES:
                print(f"    ↳ [跳过] {body_name} 已列入排除名单。")
                continue

            raw_geom = None
            if body_id and body_id != "None" and body_id in iho_features_by_id:
                raw_geom = iho_features_by_id[body_id]
            elif search_name in iho_features_by_name:
                raw_geom = iho_features_by_name[search_name]
            else:
                for db_name, geom in iho_features_by_name.items():
                    if search_name in db_name or db_name in search_name:
                        if len(search_name) > 3:
                            raw_geom = geom
                            break

            if raw_geom:
                base_water_geoms.append(raw_geom)
                successful_bodies.append(body_name)
                print(f"    ↳ [成功提取底图] {body_name}")

        if not base_water_geoms:
            print(f"    ↳ [警告] 未能找到区域 {zone_name} 的任何基础水体，跳过。")
            continue

        # 合并基础水体得到 Standard_Sea_Area
        standard_sea_area = unary_union(base_water_geoms)
        result_area = standard_sea_area

        # 3.2 空间交集运算（Intersection）：通过 JWC 提供的边界多边形裁剪水域
        jwc_boundary_coords = components.get("jwc_boundary_polygon", [])
        if jwc_boundary_coords and len(jwc_boundary_coords) > 0 and len(jwc_boundary_coords[0]) >= 3:
            try:
                jwc_boundary = Polygon(jwc_boundary_coords[0])
                if not jwc_boundary.is_valid:
                    jwc_boundary = jwc_boundary.buffer(0) # 尝试修复自交
                
                # 执行 Intersection
                result_area = standard_sea_area.intersection(jwc_boundary)
                print(f"    ↳ [执行空间交集] 已根据 JWC 边界裁剪水体。")
            except Exception as e:
                print(f"    ↳ [交集计算失败] 提供的 JWC 边界坐标无效：{e}")

        # 3.3 差集运算（Difference）：排除 12 海里领海
        exclude_12nm = components.get("exclude_12nm_coastal_waters", False)
        if exclude_12nm and coastline_12nm_buffer is not None:
            try:
                # 执行 Difference
                result_area = result_area.difference(coastline_12nm_buffer)
                print(f"    ↳ [执行空间差集] 已排除 12 海里领海水域。")
            except Exception as e:
                print(f"    ↳ [差集计算失败] 无法排除 12 海里水域：{e}")

        # 4. 生成最终结果
        if result_area.is_empty:
            print(f"    ↳ [跳过] 空间运算后结果区域为空。")
            continue

        maritime_features.append({
            "type": "Feature",
            "properties": {
                "name": zone_name,
                "details": f"Includes: {', '.join(successful_bodies)} (Custom Processed)"
            },
            "geometry": mapping(result_area)
        })

        # 为了向后兼容，提取一个简单的多边形用于特定展示
        internal_coords = []
        try:
            if isinstance(result_area, MultiPolygon):
                largest = max(result_area.geoms, key=lambda p: p.area)
                internal_coords = list(largest.exterior.coords)
            elif isinstance(result_area, Polygon):
                internal_coords = list(result_area.exterior.coords)
        except Exception:
            pass

        final_processed_zones.append({
            "name": zone_name,
            "polygon": internal_coords
        })

    # 5. 写入最终的 GeoJSON
    print(f"\n[GIS] 正在将最终运算结果写入 {output_path}...")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "type": "FeatureCollection",
            "features": maritime_features
        }, f, ensure_ascii=False)

    return final_processed_zones


def create_risk_country_geojson(countries_geojson_url: str, risk_countries: list, output_path: str):
    """过滤并生成风险国家 GeoJSON"""
    try:
        response = requests.get(countries_geojson_url, timeout=15)
        world_data = response.json()
        iso_codes = [c.get("iso_code") for c in risk_countries if c.get("iso_code")]
        risk_features = [f for f in world_data.get("features", []) if f.get("id") in iso_codes]
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": risk_features}, f, ensure_ascii=False)
    except Exception as e:
        print(f"生成国家图层失败: {e}")
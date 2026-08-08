import os
import math
import pandas as pd
import psycopg2
import folium
from folium import plugins

# ==========================================
# 1. 环境与数据库配置
# ==========================================
# 加载 .env 文件中的环境变量
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 从 .env 读取凭据
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

if not DB_USER or not DB_PASSWORD:
    raise RuntimeError("Missing DB_USER or DB_PASSWORD environment variable.")

# ==========================================
# 2. 辅助分析函数
# ==========================================
def haversine_distance(lon1, lat1, lon2, lat2):
    """
    计算两个经纬度坐标之间的距离（单位：海里 Nautical Miles）
    使用 Haversine 公式计算球面距离
    """
    # 将十进制度数转化为弧度
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
    
    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a)) 
    r = 6371 # 地球平均半径，单位为公里
    distance_km = c * r
    
    # 1 海里 = 1.852 公里
    return distance_km / 1.852


def fetch_vessel_data(mmsi, hours_back=4):
    """
    连接数据库，根据给定的 mmsi 和时间范围提取静态信息和动态轨迹数据
    """
    conn = None
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT
        )
        
        # 1. 提取静态数据 (获取船名)
        static_query = f"""
            SELECT ship_name 
            FROM "Marine Risk".vessel_static 
            WHERE mmsi = '{mmsi}';
        """
        static_df = pd.read_sql(static_query, conn)
        ship_name = static_df['ship_name'].iloc[0] if not static_df.empty and pd.notna(static_df['ship_name'].iloc[0]) else f"MMSI: {mmsi}"

        # 2. 提取动态数据 (获取过去 N 小时的轨迹)，核心要求：按 record_time 升序排列
        dynamic_query = f"""
            SELECT lon, lat, sog, cog, nav_status, record_time 
            FROM "Marine Risk".vessel_dynamic 
            WHERE mmsi = '{mmsi}' 
              AND record_time >= NOW() - INTERVAL '{hours_back} hours'
              AND lon IS NOT NULL 
              AND lat IS NOT NULL
            ORDER BY record_time ASC;
        """
        dynamic_df = pd.read_sql(dynamic_query, conn)
        
        # 确保 record_time 为字符串格式，以便后续处理为 JSON 可用的 ISO 格式
        if not dynamic_df.empty:
            dynamic_df['record_time'] = dynamic_df['record_time'].astype(str)
            
        return ship_name, dynamic_df
    
    except Exception as e:
        print(f"❌ 数据库查询失败: {e}")
        return None, pd.DataFrame()
    finally:
        if conn:
            conn.close()

# ==========================================
# 3. 核心功能：航迹回放与分析
# ==========================================
def generate_track_playback(mmsi, hours_back=24):
    print(f"正在从数据库提取 MMSI: {mmsi} 过去 {hours_back} 小时的轨迹数据...")
    ship_name, df = fetch_vessel_data(mmsi, hours_back)
    
    if df.empty:
        print(f"⚠️ 在过去 {hours_back} 小时内没有找到 MMSI {mmsi} 的有效轨迹数据。")
        return

    # --- 3.1 航行状态分析 ---
    total_distance_nm = 0.0
    for i in range(1, len(df)):
        lon1, lat1 = df.iloc[i-1]['lon'], df.iloc[i-1]['lat']
        lon2, lat2 = df.iloc[i]['lon'], df.iloc[i]['lat']
        total_distance_nm += haversine_distance(lon1, lat1, lon2, lat2)
    
    avg_sog = df['sog'].mean()
    max_sog = df['sog'].max()
    
    print(f"\n🚢 船舶名称: {ship_name}")
    print(f"📊 航行分析结果:")
    print(f"   - 提取轨迹点数: {len(df)} 个")
    print(f"   - 总航行距离: {total_distance_nm:.2f} 海里")
    print(f"   - 平均航速: {avg_sog:.2f} 节")
    print(f"   - 最大航速: {max_sog:.2f} 节")
    
    # 状态变化检测 (nav_status 发生改变的点)
    status_changes = []
    prev_status = None
    for idx, row in df.iterrows():
        curr_status = row['nav_status']
        if prev_status is not None and curr_status != prev_status:
            status_changes.append({
                'lat': row['lat'], 'lon': row['lon'],
                'old_status': prev_status, 'new_status': curr_status,
                'time': row['record_time']
            })
        prev_status = curr_status

    # --- 3.2 轨迹可视化 (Folium) ---
    center_lat = df['lat'].mean()
    center_lon = df['lon'].mean()
    # 使用深色底图，更显科技感
    m = folium.Map(location=[center_lat, center_lon], zoom_start=10, tiles="CartoDB Dark_Matter")
    
    # 构建适合 TimestampedGeoJson 的数据结构
    # TimestampedGeoJson 要求数据是一个 GeoJSON 特征集合
    features = []
    for idx, row in df.iterrows():
        feature = {
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [row['lon'], row['lat']]
            },
            'properties': {
                'time': row['record_time'],
                'popup': f"<b>{ship_name}</b><br>时间: {row['record_time']}<br>航速: {row['sog']} 节<br>航向: {row['cog']}°",
                'icon': 'circle',
                'iconstyle': {
                    'fillColor': 'cyan',
                    'fillOpacity': 0.8,
                    'stroke': 'true',
                    'radius': 5
                }
            }
        }
        features.append(feature)

    # 轨迹线我们仍然保留，为了展示整体路径
    coordinates = list(zip(df['lat'], df['lon']))
    folium.PolyLine(
        locations=coordinates,
        color='cyan',
        weight=2,
        opacity=0.5,
        tooltip=f"{ship_name} 整体航迹"
    ).add_to(m)

    # 添加时间轴动画回放插件
    plugins.TimestampedGeoJson(
        {'type': 'FeatureCollection', 'features': features},
        period='PT10M',  # 步长，可根据数据采样频率调整，如 PT1H 表示 1 小时，PT10M 表示 10 分钟
        add_last_point=True, # 保留轨迹点
        auto_play=False, # 是否自动播放
        loop=False,      # 是否循环
        max_speed=1,     # 最大播放速度
        loop_button=True,
        date_options='YYYY-MM-DD HH:mm:ss',
        time_slider_drag_update=True
    ).add_to(m)

    # 标记起点和终点
    start_point = df.iloc[0]
    end_point = df.iloc[-1]
    
    # 起点标记 (绿色)
    folium.Marker(
        [start_point['lat'], start_point['lon']],
        popup=f"<div style='width:150px'><b>🛫 起点</b><br>时间: {start_point['record_time']}</div>",
        icon=folium.Icon(color='green', icon='play', prefix='fa')
    ).add_to(m)
    
    # 终点标记 (红色)
    folium.Marker(
        [end_point['lat'], end_point['lon']],
        popup=f"<div style='width:180px'><b>🏁 终点 (最新位置)</b><br>船名: {ship_name}<br>时间: {end_point['record_time']}<br>航速: {end_point['sog']} 节<br>航向: {end_point['cog']}°</div>",
        icon=folium.Icon(color='red', icon='stop', prefix='fa')
    ).add_to(m)
    
    # 标注航行状态变化点
    for change in status_changes:
        popup_html = f"""
            <div style='width: 180px;'>
                <b>⚠️ 航行状态变更</b><br>
                时间: {change['time']}<br>
                原状态: {change['old_status']}<br>
                新状态: <b>{change['new_status']}</b>
            </div>
        """
        folium.Marker(
            [change['lat'], change['lon']],
            popup=popup_html,
            icon=folium.Icon(color='orange', icon='info-sign')
        ).add_to(m)

    # ==========================================
    # 4. 生成与保存 HTML
    # ==========================================
    output_filename = "vessel_track_playback.html"
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), output_filename)
    m.save(output_path)
    print(f"\n✅ 历史轨迹动画回放地图已成功生成！\n请在浏览器中打开此文件查看: {output_path}")

if __name__ == "__main__":
    # 使用你常用来测试的船舶 MMSI 413233370
    test_mmsi = "413233370" 
    generate_track_playback(test_mmsi, hours_back=24)

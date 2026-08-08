import os
import psycopg2
from psycopg2 import sql
from datetime import datetime
import re

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 数据库连接配置
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "postgres"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432")
}

if not DB_CONFIG["user"] or not DB_CONFIG["password"]:
    raise RuntimeError("Missing DB_USER or DB_PASSWORD environment variable.")

def clean_val(val):
    """
    清理从接口获取的值，将无意义的值转为 None (对应 SQL 里的 NULL)
    """
    if val is None or str(val).lower() == "null" or str(val).strip() == "" or str(val) == "--":
        return None
    return val

def parse_timestamp(ts_str):
    """
    尝试解析 "2025-10-14 20:59(UTC+8)" 等格式的时间戳
    如果解析失败或为空，则返回当前系统时间
    """
    ts_str = clean_val(ts_str)
    if not ts_str:
         return datetime.now()
    try:
        # 去除 (UTC+8) 这类后缀，只保留日期和时间
        clean_ts_str = re.sub(r'\(.*?\)', '', str(ts_str)).strip()
        # 尝试常用格式解析
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
            try:
                return datetime.strptime(clean_ts_str, fmt)
            except ValueError:
                continue
    except Exception:
        pass
    
    # 实在解析不出，给个当前时间作为兜底
    return datetime.now()

def parse_coordinate(coord_str):
    """
    将 "N 80度39.7752分" 或 "E 120度15.1234分" 格式的坐标转换为十进制度数
    """
    coord_str = clean_val(coord_str)
    if not coord_str:
        return None

    match = re.search(r'([NESW])\s*(\d+)度(\d+\.\d+)分', str(coord_str))
    if not match:
        return None

    direction, degrees, minutes = match.groups()
    decimal_degrees = float(degrees) + float(minutes) / 60.0
    
    if direction in ['S', 'W']:
        decimal_degrees *= -1

    return decimal_degrees

def upsert_vessel_static_data(raw_data, conn=None):
    """
    仅将 API 返回的 JSON 数据插入或更新到 vessel_static 表
    可以传入已有的 conn 以支持事务管理
    """
    if not raw_data:
        print("未收到有效数据，取消写入静态表。")
        return False

    mmsi = clean_val(raw_data.get("mmsi"))
    if not mmsi:
        print("无法获取 mmsi，无法入库。")
        return False

    imo = clean_val(raw_data.get("imo"))
    ship_name = clean_val(raw_data.get("shipname"))
    callsign = clean_val(raw_data.get("callsign"))
    length = clean_val(raw_data.get("length"))
    width = clean_val(raw_data.get("width"))
    ship_all_dun = clean_val(raw_data.get("shipAllDun"))
    
    try: length = float(length) if length is not None else None
    except ValueError: length = None
    
    try: width = float(width) if width is not None else None
    except ValueError: width = None

    try: ship_all_dun = float(ship_all_dun) if ship_all_dun is not None else None
    except ValueError: ship_all_dun = None

    close_conn = False
    cur = None
    try:
        if conn is None:
            conn = psycopg2.connect(**DB_CONFIG)
            close_conn = True
        cur = conn.cursor()

        upsert_static_query = sql.SQL("""
            INSERT INTO "Marine Risk".vessel_static (mmsi, imo, ship_name, callsign, length, width, ship_all_dun)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (mmsi) DO UPDATE SET 
                imo = EXCLUDED.imo,
                ship_name = EXCLUDED.ship_name,
                callsign = EXCLUDED.callsign,
                length = EXCLUDED.length,
                width = EXCLUDED.width,
                ship_all_dun = EXCLUDED.ship_all_dun;
        """)
        
        static_values = (mmsi, imo, ship_name, callsign, length, width, ship_all_dun)
        cur.execute(upsert_static_query, static_values)

        if close_conn:
            conn.commit()
            print(f"✅ 成功将 MMSI: {mmsi} 的静态数据写入数据库！")
        return True

    except psycopg2.Error as db_error:
        if close_conn and conn:
            conn.rollback()
        print(f"❌ 静态数据数据库操作失败: {db_error}")
        return False
    finally:
        if cur:
            cur.close()
        if close_conn and conn:
            conn.close()

def upsert_vessel_dynamic_data(raw_data, conn=None):
    """
    仅将 API 返回的 JSON 数据插入到 vessel_dynamic 表
    """
    if not raw_data:
        print("未收到有效数据，取消写入动态表。")
        return False

    mmsi = clean_val(raw_data.get("mmsi"))
    if not mmsi:
        print("无法获取 mmsi，无法入库。")
        return False

    lat = parse_coordinate(raw_data.get("latitude"))
    lon = parse_coordinate(raw_data.get("longitude"))
    
    heading = clean_val(raw_data.get("trueHeading"))
    cog = clean_val(raw_data.get("cog"))
    sog = clean_val(raw_data.get("sog"))
    eta = clean_val(raw_data.get("eta"))
    destination = clean_val(raw_data.get("destination"))
    draught = clean_val(raw_data.get("draught"))
    nav_status = clean_val(raw_data.get("navStatus"))
    record_time = parse_timestamp(raw_data.get("timeStamp"))
    
    try: heading = float(heading) if heading is not None else None
    except ValueError: heading = None
    
    try: cog = float(cog) if cog is not None else None
    except ValueError: cog = None
    
    try: sog = float(sog) if sog is not None else None
    except ValueError: sog = None
    
    try: draught = float(draught) if draught is not None else None
    except ValueError: draught = None

    if eta is not None:
         eta = str(eta)

    close_conn = False
    cur = None
    try:
        if conn is None:
            conn = psycopg2.connect(**DB_CONFIG)
            close_conn = True
        cur = conn.cursor()

        insert_dynamic_query = sql.SQL("""
            INSERT INTO "Marine Risk".vessel_dynamic 
            (mmsi, lat, lon, heading, cog, sog, eta, destination, draught, nav_status, record_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """)
        
        dynamic_values = (mmsi, lat, lon, heading, cog, sog, eta, destination, draught, nav_status, record_time)
        cur.execute(insert_dynamic_query, dynamic_values)

        if close_conn:
            conn.commit()
            print(f"✅ 成功将 MMSI: {mmsi} 的动态数据写入数据库！")
        return True

    except psycopg2.Error as db_error:
        if close_conn and conn:
            conn.rollback()
        print(f"❌ 动态数据数据库操作失败: {db_error}")
        return False
    finally:
        if cur:
            cur.close()
        if close_conn and conn:
            conn.close()

def upsert_vessel_data(raw_data):
    """
    完整写入流程：开启事务同时写入静态表和动态表 (向下兼容)
    """
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        success_static = upsert_vessel_static_data(raw_data, conn)
        success_dynamic = upsert_vessel_dynamic_data(raw_data, conn)
        
        if success_static and success_dynamic:
            conn.commit()
            print(f"✅ 成功将 MMSI: {raw_data.get('mmsi')} 的静、动态数据完整写入数据库！")
        else:
            conn.rollback()
            print(f"❌ 数据写入失败，已回滚。")
    except psycopg2.Error as db_error:
        if conn:
            conn.rollback()
        print(f"❌ 事务执行失败: {db_error}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    
    try:
        from fetch_ship_location import fetch_ship_info
        test_mmsi = "477652800"
        print(f"正在从 API 获取 MMSI {test_mmsi} 的数据...")
        data = fetch_ship_info(test_mmsi)
        
        if data:
            print("数据获取成功，准备入库...")
            upsert_vessel_data(data)
        else:
             print("未获取到数据，请检查网络或 API 是否正常。")
    except ImportError as e:
         print(f"无法导入 fetch_ship_info: {e}")

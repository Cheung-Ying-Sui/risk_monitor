import time
import schedule
from datetime import datetime
import psycopg2

# 导入我们已经写好的模块
# 假设这三个文件 (fetch_ship_location.py, loading_to_postgresql.py, automatic_fetch_dynamic_data.py) 都在同一目录下
from fetch_ship_location import fetch_ship_info
from loading_to_postgresql import upsert_vessel_data, DB_CONFIG

def get_active_mmsi_list():
    """
    从 PostgreSQL 数据库的静态表 (vessel_static) 中读取所有正在追踪的船舶 MMSI。
    如果静态表中没有数据，可以考虑在这里硬编码一个默认列表供测试使用。
    """
    mmsi_list = []
    conn = None
    cur = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        # 从静态表中查询所有的 mmsi
        cur.execute('SELECT mmsi FROM "Marine Risk".vessel_static;')
        rows = cur.fetchall()
        
        for row in rows:
            if row[0]:
                mmsi_list.append(str(row[0]))
                
    except psycopg2.Error as e:
        print(f"❌ 读取活跃 MMSI 列表失败: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
        
    return mmsi_list

def job():
    """
    定时任务：获取所有关注船舶的最新数据并写入数据库
    """
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⏳ 开始执行批量船舶动态数据更新任务...")
    
    # 获取需要追踪的船舶列表
    mmsi_list = get_active_mmsi_list()
    
    # 如果数据库里还没数据，我们就给几个默认的做测试
    if not mmsi_list:
        print("数据库中没有记录，使用默认测试 MMSI 列表。")
        mmsi_list = ["477652800", "477626369", "477205100"] 

    success_count = 0
    fail_count = 0

    for mmsi in mmsi_list:
        print(f"  -> 正在获取 MMSI: {mmsi} ...", end=" ")
        
        # 1. 调用 API 抓取最新 JSON
        data = fetch_ship_info(mmsi)
        
        if data:
            print("成功，准备写入...", end=" ")
            # 2. 调用写入脚本进行 Upsert & Insert
            # 注意: upsert_vessel_data 内部有异常处理和打印
            upsert_vessel_data(data)
            success_count += 1
        else:
            print("失败！(可能接口限流或无效MMSI)")
            fail_count += 1
            
        # 每次请求之间稍微停顿 1-2 秒，防止被 API 服务器识别为恶意爬虫而封禁 IP
        time.sleep(1.5)
        
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ 本轮任务完成！成功: {success_count}, 失败: {fail_count}")

def main():
    print("🚀 船舶动态数据自动抓取服务已启动...")
    print("配置: 每 10 分钟执行一次全量更新")
    
    # 启动时先立即执行一次
    job()
    
    # 设置定时任务：每 10 分钟执行一次 job 函数
    schedule.every(10).minutes.do(job)
    
    # 保持主线程运行，不断检查是否到了需要执行任务的时间
    try:
        while True:
            schedule.run_pending()
            # 每次循环休眠 1 秒，避免空转占用 CPU 100% 资源
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 服务已被手动停止。")

if __name__ == "__main__":
    main()
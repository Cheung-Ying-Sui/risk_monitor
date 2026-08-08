import os
import requests
import json
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def fetch_ship_info(mmsi_id):

    url = "https://ship.chinaports.com/ShipInit/shipInfo"
    chinaports_cookie = os.getenv("CHINAPORTS_COOKIE")

    # 2. 构造请求头 (从你的 F12 完整迁移)
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

    # 3. 构造请求数据 (Form Data)
    # 这里的 num 很有可能是当前毫秒级时间戳，我们动态生成它
    current_num = str(int(time.time() * 1000))

    payload = {
        "userid": mmsi_id,  # 传入你的 MMSI，例如 477652800
        "source": "0",
        "num": current_num,  # 使用动态时间戳
        "encode": "false",
        "lang": "ZH",
        "zone": "-480"
    }

    try:
        # 发送 POST 请求，将 timeout 从 10 秒增加到 30 秒
        response = requests.post(url, headers=headers, data=payload, timeout=30)

        if response.status_code == 200:
            # 解析返回的 JSON 数据
            ship_data = response.json()
            return ship_data
        else:
            print(f"请求失败，状态码: {response.status_code}")
            return None

    except Exception as e:
        print(f"发生异常: {e}")
        return None


# --- 执行查询 ---
# 由于这个文件现在经常作为模块被导入使用，为了避免在被导入时自动执行抓取逻辑（导致请求被执行两次）
# 我们将执行逻辑限制在直接运行该脚本时触发
if __name__ == "__main__":
    mmsi = "477652800"  # 你提供的标头中的 ID
    data = fetch_ship_info(mmsi)

    if data:
        print("--- 成功获取船舶实时信息 ---")
        # 格式化打印 JSON
        print(json.dumps(data, indent=4, ensure_ascii=False))

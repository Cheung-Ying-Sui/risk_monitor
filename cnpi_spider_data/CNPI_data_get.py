import os
import json
import time
import requests
import pandas as pd
import plotly.express as px


def main():
    # 1. 创建保存数据的目录
    output_dir = ""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(base_dir, output_dir)

    if not os.path.exists(output_path):
        os.makedirs(output_path)

    # 2. 初始化 Session 获取最新的 Cookie
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    print("正在获取首页 Cookie...")
    try:
        session.get("https://www.cnpi.org.cn/", headers=headers, timeout=10)
    except Exception as e:
        print(f"获取首页 Cookie 失败或超时: {e}")

    # 3. 构造 POST 请求的基础信息
    post_url = "https://www.cnpi.org.cn/visitUI.aspx"
    post_headers = headers.copy()
    post_headers["Content-Type"] = "application/x-www-form-urlencoded"
    post_headers["X-Requested-With"] = "XMLHttpRequest"
    # 【新增】加上防盗链和跨域的 Header，伪装得更像浏览器
    post_headers["Origin"] = "https://www.cnpi.org.cn"
    post_headers["Referer"] = "https://www.cnpi.org.cn/"

    # 4. 循环翻页获取所有数据
    all_data = []
    vlimit = 10
    voffset = 0
    page = 1

    print("开始循环抓取分页数据...")
    while True:
        # 【修改】使用 separators=(',', ':') 强制去掉 JSON 字符串中的空格，严格匹配浏览器的发送格式
        payload_data_str = json.dumps({"vlimit": vlimit, "voffset": voffset}, separators=(',', ':'))
        payload = {
            "Flag": "cnpiindexthree_stat",
            "Data": payload_data_str
        }

        print(f"正在请求第 {page} 页数据 (voffset={voffset})...")
        try:
            response = session.post(post_url, headers=post_headers, data=payload, timeout=10)
            response.raise_for_status()
            json_data = response.json()
        except Exception as e:
            print(f"请求第 {page} 页接口数据失败: {e}")
            break

        # 安全地获取 data 字段，如果返回的是 None 或者没这个字段，默认为空列表
        page_data = json_data.get("data") or []

        # 如果返回的 data 是空的，说明数据已经抓完，打印出服务器最后的响应以便排查
        if not page_data:
            print(f"第 {page} 页未返回数据，抓取结束。服务器响应为: {json_data}")
            break

        # 将当前页的数据追加到总列表中
        all_data.extend(page_data)
        print(f"成功获取第 {page} 页的 {len(page_data)} 条数据。")

        # 如果当前页返回的数据少于 vlimit (10条)，说明这是最后一页，退出循环
        if len(page_data) < vlimit:
            print("已到达最后一页，抓取完毕。")
            break

        # 准备抓取下一页，偏移量增加
        voffset += vlimit
        page += 1

        # 增加 1 秒延时，防止请求过快被服务器封禁 IP
        time.sleep(1)

    # 检查是否抓取到了数据
    if not all_data:
        print("未能抓取到任何数据，程序结束。")
        return

    # 5. 将完整的所有数据保存到本地 raw_data.json
    raw_data_file = os.path.join(output_path, "raw_data.json")
    with open(raw_data_file, "w", encoding="utf-8") as f:
        final_json = {"flag": "0", "data": all_data}
        json.dump(final_json, f, ensure_ascii=False, indent=4)
    print(f"共抓取到 {len(all_data)} 条原始数据，已成功保存至: {raw_data_file}")

    # 6. 数据处理与交互式可视化图表生成
    df = pd.DataFrame(all_data)

    required_cols = ['t_posteddate', 't_cnpi', 't_cndpi', 't_cntpi', 't_cncpi']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        print(f"获取的数据中缺失必要的字段: {missing_cols}")
        return

    # 日期排序
    df['t_posteddate'] = pd.to_datetime(df['t_posteddate'])
    df = df.sort_values('t_posteddate', ascending=True)

    # 将原始数据列转为数值型，并重命名为中文
    for col in ['t_cnpi', 't_cndpi', 't_cntpi', 't_cncpi']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df = df.rename(columns={
        't_cnpi': '综合指数 (CNPI)',
        't_cndpi': '干散货船指数 (CNDPI)',
        't_cntpi': '油轮/液货船指数 (CNTPI)',
        't_cncpi': '集装箱船指数 (CNCPI)'
    })

    numeric_cols = ['综合指数 (CNPI)', '干散货船指数 (CNDPI)', '油轮/液货船指数 (CNTPI)', '集装箱船指数 (CNCPI)']

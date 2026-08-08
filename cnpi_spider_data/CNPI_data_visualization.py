import os
import json
import pandas as pd
import plotly.express as px


def main():
    # 1. 定义数据读取和输出的路径
    data_dir = ""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(base_dir, data_dir)
    raw_data_file = os.path.join(data_path, "raw_data.json")

    # 检查数据文件是否存在，防止未抓取就运行报错
    if not os.path.exists(raw_data_file):
        print(f"找不到数据文件: {raw_data_file}\n请先运行 CNPI_data_get.py 抓取数据。")
        return

    # 2. 读取本地 JSON 数据
    print("正在加载本地数据...")
    with open(raw_data_file, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    # 提取核心的 data 列表
    all_data = json_data.get("data", [])
    if not all_data:
        print("本地数据文件中没有有效的 'data'，无法生成图表。")
        return

    # 3. 数据清洗与格式化
    df = pd.DataFrame(all_data)

    required_cols = ['t_posteddate', 't_cnpi', 't_cndpi', 't_cntpi', 't_cncpi']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        print(f"获取的数据中缺失必要的字段: {missing_cols}")
        return

    # 日期排序
    df['t_posteddate'] = pd.to_datetime(df['t_posteddate'])
    df = df.sort_values('t_posteddate', ascending=True)

    # 将原始数据列转为数值型，遇到无法转换的置为 NaN
    for col in ['t_cnpi', 't_cndpi', 't_cntpi', 't_cncpi']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # 图例显示
    df = df.rename(columns={
        't_cnpi': '综合指数 (CNPI)',
        't_cndpi': '干散货船指数 (CNDPI)',
        't_cntpi': '油轮/液货船指数 (CNTPI)',
        't_cncpi': '集装箱船指数 (CNCPI)'
    })

    numeric_cols = ['综合指数 (CNPI)', '干散货船指数 (CNDPI)', '油轮/液货船指数 (CNTPI)', '集装箱船指数 (CNCPI)']

    # 4. 生成彭博风格的交互式图表
    print("正在生成极致还原的彭博风格图表...")

    # 引入经典彭博配色：首发"彭博橙"，辅以青、品红、白
    bloomberg_colors = ['#DB8922', '#00FFFF', '#FF00FF', '#FFFFFF']

    fig = px.line(
        df,
        x='t_posteddate',
        y=numeric_cols,
        color_discrete_sequence=bloomberg_colors
    )

    # 复刻 theme 设置
    fig.update_layout(
        plot_bgcolor='black',
        paper_bgcolor='black',

        # 全局字体：纯白、加粗风格
        font=dict(family='Arial', size=12, color='white'),

        # 主副标题
        title=dict(
            text="<b>CNPI Index Trend</b><br><sup>China Newbuilding Price Index market trend analysis</sup>",
            x=0.01, y=0.95,
            font=dict(size=18, color='white')
        ),

        # 还原图例位置：图表内部左上方
        legend=dict(
            title_text='',
            bgcolor='rgba(0,0,0,0)',
            bordercolor='rgba(0,0,0,0)',
            orientation="h",
            yanchor="bottom", y=0.98,
            xanchor="left", x=0.01,
            font=dict(size=11)
        ),

        hovermode="x unified",
        hoverlabel=dict(bgcolor="#222222", font_size=13, font_family="Arial"),

        # 底部边距留出空间给 Source 和 Bloomberg 水印
        margin=dict(l=20, r=40, t=80, b=60)
    )

    # 复刻 X 轴：隐藏垂直网格，显示粗白底线，隐藏刻度短线
    fig.update_xaxes(
        title_text='',
        showgrid=False,
        showline=True,
        linecolor='white',
        linewidth=2,
        ticks='',
        tickfont=dict(color='white', family='Arial Black')
    )

    # 复刻 Y 轴：放右边，隐藏竖线，保留灰色虚线水平网格
    fig.update_yaxes(
        title_text='',
        side='right',
        showline=False,
        showgrid=True,
        gridcolor='grey',
        griddash='dash',
        ticks='',
        tickfont=dict(color='white', family='Arial Black')
    )

    # 左下角 Source 字样
    fig.add_annotation(
        text="Source: China Newbuilding Price Index (CNPI)",
        xref="paper", yref="paper",
        x=0, y=-0.15,
        showarrow=False,
        font=dict(size=10, color='gray')
    )

    # 右下角 Bloomberg 水印
    fig.add_annotation(
        text="<b>Bloomberg</b>",
        xref="paper", yref="paper",
        x=1, y=-0.15,
        showarrow=False,
        font=dict(size=12, color='white')
    )

    # 5. 保存 HTML 文件
    html_file = os.path.join(data_path, "bloomberg_pro_chart.html")
    fig.write_html(html_file)
    print(f"专业彭博风格图表已成功保存至: {html_file}")


if __name__ == "__main__":
    main()
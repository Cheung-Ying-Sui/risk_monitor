import streamlit as st
import os
import psycopg2
import json
import ast

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
    if val is None or str(val).strip() == "" or str(val).lower() == "null" or str(val).lower() == "na" or str(val).lower() == "tbd":
        return None
    # 尝试去除可能带有单位的字符串中的非数字部分（如果是数值字段的话，这里简化处理，直接返回原字符串/数值）
    return val

def insert_newbuilding_data(data_list):
    """
    将 JSON 列表数据插入到 PostgreSQL 的 "Marine Risk".vessel_newbuilding 表中
    """
    conn = None
    cur = None
    inserted_count = 0
    errors = []

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        insert_query = """
            INSERT INTO "Marine Risk".vessel_newbuilding 
            (
                buyer, seller, quantity, vessel_type, capacity, capacity_unit,
                builder, delivery_date, price_million_usd, fuel_type, additional_details, transaction_date
            ) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        for item in data_list:
            try:
                # 提取并清洗字段，这里的键名需与 LLM 提取的一致
                buyer = clean_val(item.get("buyer"))
                seller = clean_val(item.get("seller"))
                
                quantity = item.get("quantity")
                try: quantity = int(quantity) if quantity is not None else None
                except ValueError: quantity = None
                
                vessel_type = clean_val(item.get("vessel_type"))
                
                capacity = item.get("capacity")
                try: capacity = float(capacity) if capacity is not None else None
                except ValueError: capacity = None
                
                capacity_unit = clean_val(item.get("capacity_unit"))
                builder = clean_val(item.get("builder"))
                delivery_date = clean_val(item.get("delivery_date"))
                
                price = item.get("price_million_usd")
                try: price = float(price) if price is not None else None
                except ValueError: price = None
                
                fuel_type = clean_val(item.get("fuel_type"))
                
                # 将额外细节转为 JSON 字符串存储
                additional_details = item.get("additional_details")
                if additional_details is not None:
                     if isinstance(additional_details, (dict, list)):
                         additional_details = json.dumps(additional_details, ensure_ascii=False)
                     else:
                         additional_details = str(additional_details)
                
                transaction_date = clean_val(item.get("transaction_date"))

                values = (
                    buyer, seller, quantity, vessel_type, capacity, capacity_unit,
                    builder, delivery_date, price, fuel_type, additional_details, transaction_date
                )
                
                cur.execute(insert_query, values)
                inserted_count += 1
                
            except Exception as e:
                errors.append(f"数据行出错 {item}: {str(e)}")
                conn.rollback() # 出错回滚，但继续执行下一条（这里选择单条失败整体不回滚的策略，也可以改）
                continue

        conn.commit()
        return inserted_count, errors

    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        return 0, [f"数据库连接或事务错误: {str(e)}"]
    finally:
        if cur: cur.close()
        if conn: conn.close()


# ==========================================
# Streamlit 前端界面
# ==========================================
st.set_page_config(page_title="新造船成交数据录入", page_icon="🏗️", layout="wide")

st.title("🏗️ 新造船成交数据录入 (Newbuilding Orders)")
st.markdown("将标准化后的 JSON 数组粘贴到下方文本框中，系统将自动清洗并插入至 PostgreSQL 数据库。")

# 提供 JSON 格式示例
with st.expander("👉 查看标准 JSON 数据格式示例"):
    st.code("""
[
  {
    "buyer": "MSC",
    "seller": null,
    "quantity": 6,
    "vessel_type": "Container",
    "capacity": 19000,
    "capacity_unit": "TEU",
    "builder": "SWS",
    "delivery_date": "2027",
    "price_million_usd": 210.0,
    "fuel_type": "LNG dual-fuel",
    "additional_details": {"note": "with scrubbers"},
    "transaction_date": "2024-03-15"
  }
]
    """, language="json")

# 文本输入区域
json_input = st.text_area("📋 粘贴 JSON 数据", height=300, placeholder="[\n  {\n    \"buyer\": ...\n  }\n]")

if st.button("🚀 确认写入数据库", type="primary"):
    if not json_input.strip():
        st.warning("⚠️ 请输入 JSON 数据！")
    else:
        with st.spinner("正在解析并写入数据库..."):
            try:
                # 尝试解析 JSON
                # 有些模型可能返回带有单引号的假 JSON，ast.literal_eval 能兼容一些不标准的 dict string
                try:
                    data = json.loads(json_input)
                except json.JSONDecodeError:
                    data = ast.literal_eval(json_input)

                # 确保数据是一个列表
                if isinstance(data, dict):
                    data = [data]
                
                if not isinstance(data, list):
                    st.error("❌ 数据格式错误：必须是一个 JSON 对象或对象数组 (List of Dicts)。")
                else:
                    # 调用入库函数
                    count, errors = insert_newbuilding_data(data)
                    
                    if count > 0:
                        st.success(f"✅ 成功录入 {count} 条新造船交易记录！")
                    
                    if errors:
                        st.error(f"❌ 录入过程中发生了 {len(errors)} 个错误。")
                        with st.expander("查看错误详情"):
                            for err in errors:
                                st.write(err)

            except Exception as e:
                st.error(f"❌ 数据解析失败，请检查是否符合标准 JSON 格式。\n错误信息: {str(e)}")

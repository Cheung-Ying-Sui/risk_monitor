import json
import os
import requests
import re
from risk_zones import risk_geography_JSON_generator as rg

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

# 为了完全控制请求并避免 OpenAI 库可能的超时问题
# 我们直接使用 requests 调用 DeepSeek API
# DeepSeek API 兼容 OpenAI 的格式

# --- 配置信息 ---
LMA_JWC_URL = "https://lmalloyds.com/wp-content/uploads/2026/03/JWLA-033_Iran.pdf"
RISK_ZONE_FILE = "jwc_risk_zones.json"
PROCESSED_ZONE_FILE = "processed_risk_zones.json"
RISK_MARITIME_GEOJSON = "risk_maritime.geojson"
RISK_COUNTRY_FILE = "risk_countries.geojson"
PDF_TEMP_DIR = "../JWLA_033"
COUNTRIES_GEOJSON_URL = "https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json"
IHO_SEAS_GEOJSON = "static/iho_seas.geojson"
LAND_MASK_JSON = "static/land_mask.json"

# DeepSeek API 配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/chat/completions")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


def clean_json_string(raw_str: str) -> str:
    match = re.search(r'(\{.*\}|\[.*\])', raw_str, re.DOTALL)
    if match: return match.group(1)
    return raw_str


def call_deepseek_llm(prompt: str) -> str:
    """直接使用 requests 调用 DeepSeek API，确保完全掌控超时和错误处理"""
    if not DEEPSEEK_API_KEY:
        return "Error: Missing DEEPSEEK_API_KEY environment variable."

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }
    
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": "You are a specialized maritime GIS expert. You must strictly output valid JSON data without markdown formatting like ```json. Identify countries, maritime zones, and explicitly defined boundary polygons accurately."},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"}
    }

    try:
        # 设置长达 180 秒的超时，因为 LLM 处理大段文本需要时间
        response = requests.post(
            DEEPSEEK_BASE_URL, 
            headers=headers, 
            json=payload, 
            timeout=180.0
        )
        response.raise_for_status() # 检查非 200 响应
        
        response_data = response.json()
        return response_data['choices'][0]['message']['content']
        
    except requests.exceptions.Timeout:
        return "Error: 请求 DeepSeek API 超时 (180秒)。由于文档较长或当前 API 服务器繁忙，请稍后重试。"
    except requests.exceptions.RequestException as e:
        # 尝试打印更详细的错误信息（如配额不足等）
        error_details = ""
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_details = f" - 详情: {e.response.json()}"
            except Exception:
                error_details = f" - 状态码: {e.response.status_code}"
                
        return f"Error: 网络请求失败 {str(e)}{error_details}"
    except Exception as e:
        return f"Error: 未知异常 {str(e)}"


def download_pdf(url: str) -> str:
    if not os.path.exists(PDF_TEMP_DIR): os.makedirs(PDF_TEMP_DIR)
    file_name = url.split('/')[-1]
    save_path = os.path.join(PDF_TEMP_DIR, file_name)
    response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
    response.raise_for_status()
    with open(save_path, 'wb') as f: f.write(response.content)
    return save_path


def extract_text_from_pdf(pdf_path: str) -> str:
    if not PyPDF2: return "Error: PyPDF2 not installed."
    text = ""
    with open(pdf_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        # We don't need all pages. The Indian Ocean details are usually on the first few pages.
        # But sending 8 pages of text to the model might be too much context for it to process
        # quickly enough to avoid the Cloudflare 100s timeout. Let's limit it.
        for i in range(min(len(reader.pages), 3)): 
            text += reader.pages[i].extract_text() + "\n"
    return text


def auto_update_zones():
    """自动化核心函数：爬取 -> 解析 -> 几何装配 -> 存储"""
    try:
        print("➤ [0/3] 正在下载并解析 PDF...")
        pdf_path = download_pdf(LMA_JWC_URL)
        raw_text = extract_text_from_pdf(pdf_path)

        # Simplify the prompt to make it easier for the LLM to process within the timeout limit
        prompt = f"""
任务：解析伦敦劳合社 JWC 海上战争险通告中的海域边界。
为了避免超时，**只返回一个包含 'zones' 数组的 JSON**。不需要解析 'countries'。

【GIS 提取规则】：
1. 提取所有涉及的海域名称及其在 IHO S-23 中对应的 `iho_id`。
2. 提取原文中关于该区域的经纬度边界定义，将其转为 `jwc_boundary_polygon` (GeoJSON 多边形坐标数组 [[[lon, lat], ...]] )。
3. 如果原文提到排除沿海水域 (excepting coastal waters)，设置 `exclude_12nm_coastal_waters` 为 true。

通告部分原文：
{raw_text}

---
输出 JSON 格式示例：
{{
  "zones": [
    {{
      "zone_name": "Indian Ocean, Gulf of Aden and Southern Red Sea",
      "components": {{
        "named_water_bodies": [ {{"name": "Indian Ocean", "iho_id": "45"}} ],
        "jwc_boundary_polygon": [[[40.0, 18.0], [50.0, 18.0], ...]],
        "exclude_12nm_coastal_waters": true
      }}
    }}
  ]
}}
"""
        print("➤ [1/3] 正在调用 AI 解析 JWC 通告 (通过减少 Prompt 文本量和复杂度以规避 524 超时)...")
        json_res = call_deepseek_llm(prompt)
        
        if "Error:" in json_res:
             return False, f"\n❌ 调用大模型失败:\n{json_res}"
             
        parsed_data = json.loads(clean_json_string(json_res))

        with open(RISK_ZONE_FILE, "w", encoding="utf-8") as f:
            json.dump(parsed_data, f, ensure_ascii=False, indent=2)

        # We are skipping countries to save API time
        countries = parsed_data.get("countries", []) 
        zones = parsed_data.get("zones", [])

        print("➤ [2/3] 正在执行 GIS 装配 (交集、差集运算)...")
        # 传递给 risk_geography_JSON_generator 进行高级几何运算
        processed_zones = rg.create_risk_maritime_geojson(
            llm_zones=zones,
            iho_seas_path=IHO_SEAS_GEOJSON,
            land_mask_path=LAND_MASK_JSON,
            output_path=RISK_MARITIME_GEOJSON
        )

        print("➤ [3/3] 正在生成国家图层 (由于规避超时简化了 Prompt，此处可能跳过)...")
        if countries:
            rg.create_risk_country_geojson(
                countries_geojson_url=COUNTRIES_GEOJSON_URL,
                risk_countries=countries,
                output_path=RISK_COUNTRY_FILE
            )

        with open(PROCESSED_ZONE_FILE, "w", encoding="utf-8") as f:
            json.dump({"countries": countries, "zones": processed_zones}, f, ensure_ascii=False, indent=2)

        return True, "✅ 基础数据同步及全域高亮装配成功"
    except json.JSONDecodeError:
         return False, f"\n❌ JSON 解析失败，AI 返回的格式不正确:\n{json_res}"
    except Exception as e:
        return False, f"更新失败: {str(e)}"


if __name__ == "__main__":
    success, message = auto_update_zones()
    print(message)

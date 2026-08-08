import pandas as pd
import json
import os


def get_vessel_country_code(vessel_row: pd.Series) -> str:
    """提取 ISO 代码的辅助函数"""
    if 'iso_code' in vessel_row and pd.notna(vessel_row['iso_code']):
        return str(vessel_row['iso_code']).upper()
    return str(vessel_row.get('country_iso', '')).upper()


def load_processed_vessels() -> pd.DataFrame:
    """加载并预处理船舶数据，确保关键列存在"""
    file_path = "latest_vessel_positions.json"
    if not os.path.exists(file_path):
        return pd.DataFrame(columns=['name', 'lat', 'lon', 'is_alert', 'country_iso', 'description'])

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            df = pd.DataFrame(data.values())

            if df.empty:
                return df

            # 统一列名与默认值
            if 'is_alert' not in df.columns:
                df['is_alert'] = False

            df['country_iso'] = df.apply(get_vessel_country_code, axis=1)
            
            # 为地图 tooltip 准备 name 和 description 字段
            df = df.rename(columns={"vessel_name": "name"})
            df["description"] = df.apply(
                lambda row: f"Status: {'Alert' if row.get('is_alert') else 'Normal'}<br>"
                            f"Location: ({row.get('lat', 0):.2f}, {row.get('lon', 0):.2f})",
                axis=1
            )
            
            # 仅保留必要列并重置索引，防止非法列名（如数字开头）或索引导致 PyDeck 报错
            # Error: Variable names cannot start with a number
            safe_cols = ['name', 'lat', 'lon', 'is_alert', 'country_iso', 'description']
            for col in safe_cols:
                if col not in df.columns:
                    df[col] = None
            return df[safe_cols].reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=['name', 'lat', 'lon', 'is_alert', 'country_iso', 'description'])


def filter_vessels(df: pd.DataFrame, iso_code: str) -> pd.DataFrame:
    """按国家筛选船舶"""
    if iso_code == "ALL" or df.empty:
        return df
    return df[df['country_iso'] == iso_code]

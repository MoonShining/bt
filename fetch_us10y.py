"""
获取美国10年期国债收益率数据
使用 akshare 获取，保存为 CSV 文件供回测使用
"""

import akshare as ak
import pandas as pd
import os


def fetch_us10y_rate() -> pd.DataFrame:
    """
    获取美国10年期国债收益率历史数据
    返回: DataFrame 包含日期和收益率
    """
    print("正在从 akshare 获取美国国债收益率数据...")
    df = ak.bond_zh_us_rate()
    print(f"获取完成，共 {len(df)} 条数据")

    # 整理数据格式
    df = df.rename(columns={
        "日期": "date",
        "美国国债收益率10年": "us10y"
    })

    # 按日期排序
    df = df.sort_values("date").reset_index(drop=True)

    return df


def save_us10y_to_csv(filepath: str = "./us10y_daily.csv"):
    """保存美债收益率数据到CSV文件"""
    df = fetch_us10y_rate()
    df.to_csv(filepath, index=False)
    print(f"数据已保存到 {filepath}")
    print(f"时间范围: {df['date'].min()} 至 {df['date'].max()}")
    print(f"最新收益率: {df.iloc[-1]['us10y']:.2f}%")
    return df


def load_us10y_from_csv(filepath: str = "./us10y_daily.csv") -> pd.DataFrame:
    """从CSV加载美债收益率数据"""
    if not os.path.exists(filepath):
        print(f"文件 {filepath} 不存在，正在重新获取...")
        return save_us10y_to_csv(filepath)

    df = pd.read_csv(filepath)
    df['date'] = pd.to_datetime(df['date']).dt.date
    print(f"已加载 {len(df)} 条美债收益率数据")
    print(f"时间范围: {df['date'].min()} 至 {df['date'].max()}")
    return df


def get_us10y_on_date(date, df: pd.DataFrame) -> float:
    """根据日期获取对应的美债收益率，找不到返回上一个可用数据"""
    # 转换为date对象
    if hasattr(date, 'date'):
        date = date.date()
    if hasattr(date, 'to_pydate'):
        date = date.to_pydate()

    # 查找 exact match
    match = df[df['date'] == date]
    if not match.empty:
        return match.iloc[0]['us10y']

    # 找不到，找日期之前的最后一个数据
    prev = df[df['date'] < date]
    if not prev.empty:
        return prev.iloc[-1]['us10y']

    # 找不到任何数据，返回NaN
    return float('nan')


if __name__ == "__main__":
    save_us10y_to_csv()

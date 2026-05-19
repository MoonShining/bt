"""
获取长江电力(600900)历史数据
保存为CSV供回测使用
"""

import akshare as ak
import pandas as pd
import os


def fetch_stock_data(code: str = "600900", name: str = "cdp") -> pd.DataFrame:
    """
    获取A股股票历史数据
    code: 股票代码
    name: 保存名称
    """
    print(f"正在获取 {code} 历史数据...")
    df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date="20030101", end_date="20261231", adjust="qfq")

    print(f"获取完成，共 {len(df)} 条数据")

    # 转换为backtrader兼容的格式
    # backtrader需要列名: Date, Open, High, Low, Close, Volume
    df = df.rename(columns={
        "日期": "Date",
        "开盘": "Open",
        "最高": "High",
        "最低": "Low",
        "收盘": "Close",
        "成交量": "Volume"
    })

    # 日期格式转换
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.set_index('Date')
    df = df.sort_index()

    # 保存
    output_path = f"./{name}_daily.csv"
    df.to_csv(output_path)
    print(f"数据已保存到 {output_path}")
    print(f"时间范围: {df.index.min()} 至 {df.index.max()}")
    print(f"最新收盘价: {df.iloc[-1]['Close']:.2f}")

    return df


if __name__ == "__main__":
    fetch_stock_data("600900", "cdp")  # 长江电力

#!/usr/bin/env python3
"""
使用 akshare 获取上证指数数据
导出为与 orcl-1995-2014.txt 相同格式的 CSV 文件
格式：Date,Open,High,Low,Close,Adj Close,Volume
"""

import akshare as ak
import pandas as pd

def fetch_sh_index(start_date=None, end_date=None):
    """
    获取上证指数日线数据
    """
    print("正在获取上证指数日线数据...")
    # 获取上证指数日线数据
    df = ak.stock_zh_index_daily(symbol="sh000001")

    # akshare 返回格式：date, open, high, low, close, volume
    # 需要重新命名并添加 Adj Close 列
    df = df.rename(columns={
        'date': 'Date',
        'open': 'Open',
        'high': 'High',
        'low': 'Low',
        'close': 'Close',
        'volume': 'Volume',
    })

    # 确保 Date 列是 datetime 类型
    df['Date'] = pd.to_datetime(df['Date'])

    # 添加 Adj Close 列，这里 Close 和 Adj Close 使用相同值
    # 因为上证指数不需要复权，保持一致即可
    df['Adj Close'] = df['Close']

    # 调整列顺序匹配目标格式
    df = df[['Date', 'Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']]

    # 如果指定了起止日期，过滤
    if start_date:
        df = df[df['Date'] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df['Date'] <= pd.to_datetime(end_date)]

    # 按日期升序排列
    df = df.sort_values('Date').reset_index(drop=True)

    return df

def main():
    # 获取从 1990 年到现在的所有数据
    df = fetch_sh_index(start_date="1991-01-01", end_date=None)

    print(f"\n获取到数据：")
    print(f"共 {len(df)} 个交易日")
    print(f"起始日期: {df['Date'].min()}")
    print(f"结束日期: {df['Date'].max()}")
    print(f"\n前5行：")
    print(df.head())
    print(f"\n后5行：")
    print(df.tail())

    # 保存为 CSV，格式和 orcl 一致
    output_file = "sh000001_daily.csv"
    df.to_csv(output_file, index=False)

    print(f"\n数据已保存到 {output_file}")
    print(f"文件格式：Date,Open,High,Low,Close,Adj Close,Volume")

if __name__ == "__main__":
    main()

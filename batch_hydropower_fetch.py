#!/usr/bin/env python3
"""
批量获取水电股票日线数据
类似长江电力的大型水电公司
"""

import akshare as ak
import pandas as pd
import os

# 水电股票列表
STOCKS = [
    ("600886", "国投电力", "600886_daily.csv"),
    ("600236", "桂冠电力", "600236_daily.csv"),
    ("600025", "华能水电", "600025_daily.csv"),
    ("600674", "川投能源", "600674_daily.csv"),
]

def fetch_stock_daily(symbol: str, name: str) -> pd.DataFrame:
    """获取单只股票日线数据"""
    print(f"正在获取 {name}({symbol}) 日线数据...")

    # 判断是沪市还是深市
    if symbol.startswith('6'):
        ak_symbol = f"sh{symbol}"
    else:
        ak_symbol = f"sz{symbol}"

    df = ak.stock_zh_index_daily(symbol=ak_symbol)

    df = df.rename(columns={
        'date': 'Date',
        'open': 'Open',
        'high': 'High',
        'low': 'Low',
        'close': 'Close',
        'volume': 'Volume',
    })

    df['Date'] = pd.to_datetime(df['Date'])
    df['Adj Close'] = df['Close']
    df = df[['Date', 'Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']]
    df = df.sort_values('Date').reset_index(drop=True)

    return df

def main():
    for symbol, name, output_file in STOCKS:
        if os.path.exists(output_file):
            print(f"\n{output_file} 已存在，跳过下载")
            df = pd.read_csv(output_file)
            print(f"  已有数据: {len(df)} 行，从 {df.iloc[0]['Date']} 到 {df.iloc[-1]['Date']}")
            continue

        print(f"\n{'='*60}")
        try:
            df = fetch_stock_daily(symbol, name)
            print(f"  获取成功：共 {len(df)} 个交易日")
            print(f"  起始日期: {df['Date'].min()}")
            print(f"  结束日期: {df['Date'].max()}")

            df.to_csv(output_file, index=False)
            print(f"  已保存到 {output_file}")
        except Exception as e:
            print(f"  获取失败: {e}")

    print(f"\n{'='*60}")
    print("全部完成！")

if __name__ == "__main__":
    main()

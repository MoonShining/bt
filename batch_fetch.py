#!/usr/bin/env python3
"""
批量获取 A 股股票日线数据
使用 akshare 获取，导出为回测可用的 CSV 格式
格式：Date,Open,High,Low,Close,Adj Close,Volume
"""

import akshare as ak
import pandas as pd
import os

# 三个梯队股票列表
STOCKS = [
    # 第一梯队
    ("600900", "长江电力", "cdp_daily.csv"),  # 已有
    ("600377", "宁沪高速", "600377_daily.csv"),
    # 第二梯队
    ("601006", "大秦铁路", "601006_daily.csv"),
    ("600012", "皖通高速", "600012_daily.csv"),
    # 第三梯队
    ("601088", "中国神华", "601088_daily.csv"),
    ("601398", "工商银行", "601398_daily.csv"),
]

def fetch_stock_daily(symbol: str, name: str) -> pd.DataFrame:
    """
    获取单只股票日线数据
    symbol: 6位代码
    """
    # akshare 的 A 股日线接口
    print(f"正在获取 {name}({symbol}) 日线数据...")

    # 判断是沪市还是深市
    if symbol.startswith('6'):
        ak_symbol = f"sh{symbol}"
    else:
        ak_symbol = f"sz{symbol}"

    df = ak.stock_zh_index_daily(symbol=ak_symbol)

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

    # 添加 Adj Close 列，这里使用前复权思路，Close 已经是复权后的价格
    # 我们直接让 Adj Close = Close
    df['Adj Close'] = df['Close']

    # 调整列顺序匹配目标格式
    df = df[['Date', 'Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']]

    # 按日期升序排列
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

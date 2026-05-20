#!/usr/bin/env python3
"""
参数优化 - 均值回归策略
对长江电力和国投电力进行网格搜索，寻找最优参数组合
"""

import subprocess
import os
import pandas as pd
from dataclasses import dataclass
from typing import Optional

# 要优化的股票
STOCKS = [
    ("600900", "长江电力", "cdp_daily.csv"),
    ("600886", "国投电力", "600886_daily.csv"),
]

# 参数网格
# 布林带周期
BB_PERIODS = [10, 15, 20, 25, 30]
# 标准差倍数
BB_DEVS = [1.5, 1.8, 2.0, 2.2, 2.5]
# 止损比例
STOP_LOSSES = [0.10, 0.15, 0.20, 0.25, 0.30]

STRATEGY = "mean"
INITIAL_CASH = 100000.0

@dataclass
class Result:
    code: str
    name: str
    bb_period: int
    bb_dev: float
    stop_loss: float
    total_return: float
    annualized_return: float
    sharpe: float
    max_drawdown: float
    total_trades: int
    win_rate: float
    final_cash: float
    success: bool

def run_backtest(code, name, data_file, bb_period, bb_dev, stop_loss):
    """运行单次回测"""
    cmd = (
        f"python3 main.py "
        f"--strategy {STRATEGY} "
        f"--data {data_file} "
        f"--bb-period {bb_period} "
        f"--bb-dev {bb_dev} "
        f"--stop-loss {stop_loss}"
    )

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    parsed = parse_output(result.stdout)
    parsed['code'] = code
    parsed['name'] = name
    parsed['bb_period'] = bb_period
    parsed['bb_dev'] = bb_dev
    parsed['stop_loss'] = stop_loss

    return parsed

def parse_output(output):
    """解析输出"""
    result = {
        'success': False,
        'total_return': None,
        'annualized_return': None,
        'sharpe': None,
        'max_drawdown': None,
        'total_trades': None,
        'win_rate': None,
        'final_cash': None,
    }

    lines = output.strip().split('\n')
    in_result = False

    for line in lines:
        line = line.strip()
        if '[回测结果]' in line:
            in_result = True
            continue
        if not in_result:
            continue
        if '-'*50 in line:
            if result['total_return'] is not None:
                break
            continue

        if line.startswith('收益率:'):
            try:
                pct = float(line.split(':')[1].strip().replace('%', '')) / 100
                result['total_return'] = pct
            except:
                pass
        elif line.startswith('年化收益率:'):
            try:
                pct = float(line.split(':')[1].strip().replace('%', ''))
                result['annualized_return'] = pct
            except:
                pass
        elif line.startswith('夏普比率:'):
            val = line.split(':')[1].strip()
            if val != 'N/A':
                try:
                    result['sharpe'] = float(val)
                except:
                    pass
        elif line.startswith('最大回撤:'):
            try:
                pct = float(line.split(':')[1].strip().replace('%', ''))
                result['max_drawdown'] = pct
            except:
                pass
        elif line.startswith('总交易次数:'):
            try:
                val = int(line.split(':')[1].strip())
                result['total_trades'] = val
            except:
                pass
        elif line.startswith('胜率:'):
            try:
                pct_part = line.split(':')[1].strip().split('%')[0]
                pct = float(pct_part) / 100
                result['win_rate'] = pct
            except:
                pass
        elif line.startswith('[最终] 资金:'):
            try:
                val = float(line.split(':')[1].strip().replace(',', ''))
                result['final_cash'] = val
                result['success'] = True
            except:
                pass

    return result

def main():
    results = []
    total_combinations = len(BB_PERIODS) * len(BB_DEVS) * len(STOP_LOSSES) * len(STOCKS)
    current = 0

    print(f"{'='*80}")
    print(f"开始参数优化，总共 {total_combinations} 个参数组合")
    print(f"参数网格:")
    print(f"  BB_PERIOD: {BB_PERIODS}")
    print(f"  BB_DEV: {BB_DEVS}")
    print(f"  STOP_LOSS: {STOP_LOSSES}")
    print(f"{'='*80}")

    for code, name, data_file in STOCKS:
        print(f"\n{'='*80}")
        print(f"正在优化: {name}({code})")
        print(f"{'='*80}")

        for bb_period in BB_PERIODS:
            for bb_dev in BB_DEVS:
                for stop_loss in STOP_LOSSES:
                    current += 1
                    print(f"\n[{current}/{total_combinations}] "
                          f"{name} - period={bb_period}, dev={bb_dev}, stop={stop_loss:.0%}")

                    if not os.path.exists(data_file):
                        print(f"  数据文件 {data_file} 不存在，跳过")
                        continue

                    res = run_backtest(code, name, data_file, bb_period, bb_dev, stop_loss)
                    if res['success']:
                        results.append(Result(**res))
                        print(f"  ✓ 完成: 年化={res['annualized_return']:.2f}%, 夏普={res['sharpe']:.2f}, 最大回撤={res['max_drawdown']:.2f}%")
                    else:
                        print(f"  ✗ 失败")

    # 整理结果为DataFrame
    df = pd.DataFrame([
        {
            'code': r.code,
            'name': r.name,
            'bb_period': r.bb_period,
            'bb_dev': r.bb_dev,
            'stop_loss': r.stop_loss,
            'total_return': r.total_return,
            'annualized_return': r.annualized_return,
            'sharpe': r.sharpe,
            'max_drawdown': r.max_drawdown,
            'total_trades': r.total_trades,
            'win_rate': r.win_rate,
            'final_cash': r.final_cash,
        }
        for r in results if r.success
    ])

    # 按股票分组，分别排序
    for code in df['code'].unique():
        print(f"\n\n{'='*80}")
        print(f"参数优化结果 - {code} {df[df['code'] == code]['name'].iloc[0]}")
        print(f"{'='*80}")

        code_df = df[df['code'] == code].copy()

        # 按年化收益率排序（降序）
        code_df_sorted = code_df.sort_values('annualized_return', ascending=False).reset_index(drop=True)

        print("\n📈 按年化收益率排序 TOP 10:")
        print("-"*100)
        print(f"{'排名':<4} {'周期':<6} {'标准差':<8} {'止损':<8} {'年化%':<8} {'夏普':<6} {'最大回撤%':<10} {'胜率%':<8} {'交易数'}")
        print("-"*100)
        for i, row in code_df_sorted.head(10).iterrows():
            print(f"{i+1:<4} {row['bb_period']:<6} {row['bb_dev']:<8.1f} "
                  f"{row['stop_loss']:<8.0%} {row['annualized_return']:<8.2f} "
                  f"{row['sharpe']:<6.2f} {row['max_drawdown']:<10.2f} "
                  f"{row['win_rate']*100:<8.1f} {row['total_trades']}")

        # 按夏普比率排序
        print(f"\n📊 按夏普比率排序 TOP 10（风险调整后收益）:")
        print("-"*100)
        code_df_sharpe = code_df.sort_values('sharpe', ascending=False).reset_index(drop=True)
        print(f"{'排名':<4} {'周期':<6} {'标准差':<8} {'止损':<8} {'年化%':<8} {'夏普':<6} {'最大回撤%':<10} {'胜率%':<8} {'交易数'}")
        print("-"*100)
        for i, row in code_df_sharpe.head(10).iterrows():
            print(f"{i+1:<4} {row['bb_period']:<6} {row['bb_dev']:<8.1f} "
                  f"{row['stop_loss']:<8.0%} {row['annualized_return']:<8.2f} "
                  f"{row['sharpe']:<6.2f} {row['max_drawdown']:<10.2f} "
                  f"{row['win_rate']*100:<8.1f} {row['total_trades']}")

        # 找最大回撤较小的
        print(f"\n🛡️  最大回撤 < 40% 且年化 > 5% 的优质参数:")
        print("-"*100)
        good = code_df[(code_df['max_drawdown'] < 40) & (code_df['annualized_return'] > 5)]
        good = good.sort_values('sharpe', ascending=False).reset_index(drop=True)
        if len(good) > 0:
            print(f"{'排名':<4} {'周期':<6} {'标准差':<8} {'止损':<8} {'年化%':<8} {'夏普':<6} {'最大回撤%':<10} {'胜率%':<8} {'交易数'}")
            print("-"*100)
            for i, row in good.head(10).iterrows():
                print(f"{i+1:<4} {row['bb_period']:<6} {row['bb_dev']:<8.1f} "
                      f"{row['stop_loss']:<8.0%} {row['annualized_return']:<8.2f} "
                      f"{row['sharpe']:<6.2f} {row['max_drawdown']:<10.2f} "
                      f"{row['win_rate']*100:<8.1f} {row['total_trades']}")
        else:
            print("  没有符合条件的参数")

    # 保存完整结果
    df.to_csv("parameter_optimization_result.csv", index=False)
    print(f"\n\n完整结果已保存到 parameter_optimization_result.csv")

    # 生成markdown报告
    with open("parameter_optimization_result.md", "w", encoding="utf-8") as f:
        f.write("# 均值回归策略参数优化结果\n\n")
        f.write(f"策略: 布林带均值回归\n")
        f.write(f"优化股票: 长江电力(600900) + 国投电力(600886)\n\n")
        f.write(f"参数网格搜索:\n")
        f.write(f"- 布林带周期: {BB_PERIODS}\n")
        f.write(f"- 标准差倍数: {BB_DEVS}\n")
        f.write(f"- 止损比例: {[f'{x:.0%}' for x in STOP_LOSSES]}\n\n")
        f.write(f"总参数组合: {total_combinations}\n\n")

        for code in df['code'].unique():
            name = df[df['code'] == code]['name'].iloc[0]
            f.write(f"## {code} {name}\n\n")

            code_df = df[df['code'] == code].copy()

            # TOP 10 年化
            f.write("### 按年化收益率排序 TOP 10\n\n")
            f.write("| 排名 | 布林周期 | 标准差 | 止损 | 年化收益率 | 夏普比率 | 最大回撤 | 胜率 | 交易次数 |\n")
            f.write("|:----:|:--------:|:-------:|:-----:|-----------:|---------:|---------:|-------:|---------:|\n")
            code_df_sorted = code_df.sort_values('annualized_return', ascending=False).reset_index(drop=True)
            for i, row in code_df_sorted.head(10).iterrows():
                f.write(f"| {i+1} | {row['bb_period']} | {row['bb_dev']:.1f} | {row['stop_loss']:.0%} | "
                      f"{row['annualized_return']:.2f}% | {row['sharpe']:.2f} | {row['max_drawdown']:.2f}% | "
                      f"{row['win_rate']*100:.1f}% | {row['total_trades']} |\n")
            f.write("\n")

            # TOP 10 夏普
            f.write("### 按夏普比率排序 TOP 10 (风险调整后收益)\n\n")
            f.write("| 排名 | 布林周期 | 标准差 | 止损 | 年化收益率 | 夏普比率 | 最大回撤 | 胜率 | 交易次数 |\n")
            f.write("|:----:|:--------:|:-------:|:-----:|-----------:|---------:|---------:|-------:|---------:|\n")
            code_df_sharpe = code_df.sort_values('sharpe', ascending=False).reset_index(drop=True)
            for i, row in code_df_sharpe.head(10).iterrows():
                f.write(f"| {i+1} | {row['bb_period']} | {row['bb_dev']:.1f} | {row['stop_loss']:.0%} | "
                      f"{row['annualized_return']:.2f}% | {row['sharpe']:.2f} | {row['max_drawdown']:.2f}% | "
                      f"{row['win_rate']*100:.1f}% | {row['total_trades']} |\n")
            f.write("\n")

            # 优质参数（低回撤+高收益）
            f.write("### 优质参数筛选（最大回撤 < 40% 且 年化 > 5%）\n\n")
            f.write("| 排名 | 布林周期 | 标准差 | 止损 | 年化收益率 | 夏普比率 | 最大回撤 | 胜率 | 交易次数 |\n")
            f.write("|:----:|:--------:|:-------:|:-----:|-----------:|---------:|---------:|-------:|---------:|\n")
            good = code_df[(code_df['max_drawdown'] < 40) & (code_df['annualized_return'] > 5)]
            good = good.sort_values('sharpe', ascending=False).reset_index(drop=True)
            if len(good) > 0:
                for i, row in good.iterrows():
                    f.write(f"| {i+1} | {row['bb_period']} | {row['bb_dev']:.1f} | {row['stop_loss']:.0%} | "
                          f"{row['annualized_return']:.2f}% | {row['sharpe']:.2f} | {row['max_drawdown']:.2f}% | "
                          f"{row['win_rate']*100:.1f}% | {row['total_trades']} |\n")
            else:
                f.write("| 无符合条件参数 |\n")
            f.write("\n")

    print(f"markdown报告已保存到 parameter_optimization_result.md")

if __name__ == "__main__":
    main()

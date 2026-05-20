#!/usr/bin/env python3
"""
批量回测均值回归策略 - 水电板块（类似长江电力）
"""

import subprocess
import json
import pandas as pd
import os
from datetime import datetime

# 回测配置
STOCKS = [
    ("水电", "600886", "国投电力", "600886_daily.csv"),
    ("水电", "600236", "桂冠电力", "600236_daily.csv"),
    ("水电", "600025", "华能水电", "600025_daily.csv"),
    ("水电", "600674", "川投能源", "600674_daily.csv"),
]

# 策略参数（和长江电力回测保持一致）
STRATEGY = "mean"
BB_PERIOD = 20
BB_DEV = 2.0
STOP_LOSS = 0.20  # 20% 止损
INITIAL_CASH = 100000.0

def run_backtest(echelon, code, name, data_file):
    """运行单次回测"""
    print(f"\n{'='*70}")
    print(f"开始回测: {echelon} - {name}({code}) - {data_file}")
    print(f"{'='*70}")

    # 构建命令
    cmd = (
        f"python3 main.py "
        f"--strategy {STRATEGY} "
        f"--data {data_file} "
        f"--bb-period {BB_PERIOD} "
        f"--bb-dev {BB_DEV} "
        f"--stop-loss {STOP_LOSS}"
    )

    print(f"执行命令: {cmd}")
    print()

    # 执行并捕获输出
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    # 输出到控制台
    print(result.stdout)
    if result.stderr:
        print("STDERR:")
        print(result.stderr)

    # 解析结果
    parsed = parse_output(result.stdout)
    parsed['echelon'] = echelon
    parsed['code'] = code
    parsed['name'] = name
    parsed['data_file'] = data_file
    parsed['return_code'] = result.returncode

    return parsed

def parse_output(output):
    """从标准输出解析回测结果"""
    result = {
        'success': False,
        'total_return': None,
        'annualized_return': None,
        'sharpe': None,
        'max_drawdown': None,
        'max_drawdown_days': None,
        'total_trades': None,
        'win_rate': None,
        'won': None,
        'lost': None,
        'final_cash': None,
        'start_date': None,
        'end_date': None,
    }

    lines = output.strip().split('\n')

    # 查找回测结果区块
    in_result = False
    for line in lines:
        line = line.strip()
        if '[回测结果]' in line:
            in_result = True
            continue
        if not in_result:
            # 解析时间范围
            if line.startswith('[时间范围]'):
                parts = line.split()
                if len(parts) >= 5:
                    result['start_date'] = parts[3]
                    result['end_date'] = parts[5]
            continue
        if '-'*50 in line:
            if result['total_return'] is not None:
                break  # 已经到了最终资金区块，结束
            continue

        if line.startswith('总收益:'):
            continue  # 这个是绝对值，我们需要收益率
        elif line.startswith('收益率:'):
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
        elif line.startswith('最大回撤持续天数:'):
            try:
                val = int(line.split(':')[1].strip())
                result['max_drawdown_days'] = val
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
                if '(' in line and '胜' in line and '负' in line:
                    parts = line.split('(')[1].split(')')[0].split()
                    for p in parts:
                        if '胜' in p:
                            result['won'] = int(p.split('胜')[0])
                        if '负' in p:
                            result['lost'] = int(p.split('负')[0])
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

    for echelon, code, name, data_file in STOCKS:
        if not os.path.exists(data_file):
            print(f"\n警告: {data_file} 不存在，跳过 {name}")
            continue

        res = run_backtest(echelon, code, name, data_file)
        results.append(res)

    # 输出汇总表格
    print("\n\n")
    print("="*80)
    print(" " * 20 + "水电股均值回归回测结果汇总表")
    print("="*80)
    print()

    # Markdown 表格
    header = (
        f"| 代码 | 名称 | 总收益率 | 年化收益率 | 夏普比率 | 最大回撤 | "
        f"交易次数 | 胜率 | 回测年限 |\n"
        f"|:----:|:----|---------:|-----------:|---------:|---------:|---------:|-------:|:----------|\n"
    )
    print(header)

    md_lines = [
        "# 水电股均值回归策略回测结果（类似长江电力）\n\n",
        f"策略参数: 布林带周期={BB_PERIOD}, 标准差={BB_DEV}, 固定止损={STOP_LOSS:.0%}\n\n",
        f"初始资金: {INITIAL_CASH:.0f}, 佣金: 0.1%\n\n",
        header
    ]

    for res in results:
        if not res['success']:
            continue

        # 计算回测年限
        if res['start_date'] and res['end_date']:
            try:
                start = datetime.strptime(res['start_date'], "%Y-%m-%d")
                end = datetime.strptime("2026-12-31", "%Y-%m-%d")
                years = (end - start).days / 365.25
                years_str = f"{res['start_date'][:4]}~2026 ({years:.0f}年)"
            except:
                years_str = f"{res['start_date']} ~ {res['end_date']}"
        else:
            years_str = "-"

        line = (
            f"| {res['code']} | {res['name']} | "
            f"{res['total_return']:.2%} | {res['annualized_return']:.2f}% | "
            f"{res['sharpe']:.2f} | {res['max_drawdown']:.2f}% | "
            f"{res['total_trades']} | {res['win_rate']:.2%} | "
            f"{years_str} |\n"
        )
        print(line, end='')
        md_lines.append(line)

    print()
    print("-"*80)
    print(f"对比基准: 长江电力 600900 → 总收益+195.39%, 年化+5.57%, 夏普0.46, 最大回撤27.28%")
    print()

    # 保存汇总结果
    with open("batch_hydropower_result.md", "w", encoding="utf-8") as f:
        f.writelines(md_lines)

    # 添加对比基准
    with open("batch_hydropower_result.md", "a", encoding="utf-8") as f:
        f.write(f"\n对比基准（第一回测结果）:\n")
        f.write(f"- 长江电力 600900: **总收益 +195.39%, 年化 +5.57%, 夏普 0.46, 最大回撤 27.28%**\n")

    print(f"汇总结果已保存到 batch_hydropower_result.md")

if __name__ == "__main__":
    main()

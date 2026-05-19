import datetime
import os
import argparse
import backtrader as bt
import backtrader.analyzers as btanalyzers

from notifier import create_notifier
from ai import MultiPeriodTrendStrategy as TrendFollowStrategy
from mean_reversion import BollingerMeanReversionStrategy as MeanReversionStrategy

parser = argparse.ArgumentParser(description="回测系统")
parser.add_argument(
    "--plot",
    action="store_true",
    help="开启绘图模式"
)
parser.add_argument(
    "--strategy", "-s",
    type=str,
    default="trend",
    help="选择策略: trend(趋势跟随), mean(均值回归)"
)
parser.add_argument(
    "--data", "-d",
    type=str,
    default="./sh000001_daily.csv",
    help="数据文件路径 (默认: ./sh000001_daily.csv, 长江电力: ./cdp_daily.csv)"
)
parser.add_argument(
    "--us10y-filter", "-u",
    action="store_true",
    help="启用美债收益率宏观过滤 (仅趋势策略)"
)
parser.add_argument(
    "--us10y-high",
    type=float,
    default=4.5,
    help="美债高收益率阈值(%%)，超过禁止开新仓 (默认: 4.5)"
)
parser.add_argument(
    "--us10y-low",
    type=float,
    default=3.0,
    help="美债低收益率阈值(%%)，低于不压缩仓位 (默认: 3.0)"
)
parser.add_argument(
    "--bb-period",
    type=int,
    default=20,
    help="布林带周期 (均值回归策略，默认: 20)"
)
parser.add_argument(
    "--bb-dev",
    type=float,
    default=2.0,
    help="布林带标准差倍数 (均值回归策略，默认: 2.0)"
)
parser.add_argument(
    "--stop-loss",
    type=float,
    default=0.15,
    help="止损比例 (均值回归策略，默认: 0.15 = 15%%)"
)
args = parser.parse_args()

# 创建通知器（如果配置了 Server酱 则使用，否则使用控制台）
notifier = create_notifier(os.getenv("WECHAT_SEND_KEY", ""))
# notifier.send("回测结果", "测试消息\n\n第二行")

if __name__ == '__main__':
    cerebro = bt.Cerebro()

    # 策略参数
    strategy_kwargs = {}

    # 美债过滤参数
    if args.us10y_filter:
        strategy_kwargs['enable_us10y_filter'] = True
        strategy_kwargs['us10y_high_threshold'] = args.us10y_high
        strategy_kwargs['us10y_low_threshold'] = args.us10y_low
        print(f"[配置] 启用美债收益率过滤，高阈值={args.us10y_high}%, 低阈值={args.us10y_low}%")

    if args.strategy == "trend":
        cerebro.addstrategy(TrendFollowStrategy, **strategy_kwargs)
        strategy_name = "多周期趋势跟随"
        if args.us10y_filter:
            strategy_name += "（美债过滤版）"
    elif args.strategy == "mean":
        # 均值回归策略参数
        strategy_kwargs['bb_period'] = args.bb_period
        strategy_kwargs['bb_dev'] = args.bb_dev
        strategy_kwargs['stop_loss_pct'] = args.stop_loss
        cerebro.addstrategy(MeanReversionStrategy, **strategy_kwargs)
        strategy_name = f"布林带均值回归(周期={args.bb_period}, σ={args.bb_dev})"
        print(f"[配置] 均值回归策略，布林带周期={args.bb_period}, 标准差={args.bb_dev}, 止损={args.stop_loss:.1%}")
    else:
        print(f"未知策略: {args.strategy}，使用默认趋势跟随")
        cerebro.addstrategy(TrendFollowStrategy, **strategy_kwargs)
        strategy_name = "多周期趋势跟随"
        if args.us10y_filter:
            strategy_name += "（美债过滤版）"

    # 添加分析器
    cerebro.addanalyzer(btanalyzers.Returns, _name='returns')
    cerebro.addanalyzer(btanalyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(btanalyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(btanalyzers.SharpeRatio, _name='sharpe', timeframe=bt.TimeFrame.Years)

    datapath = args.data

    # 根据策略和数据设置时间范围
    if 'cdp' in datapath:
        # 长江电力从2003年上市开始
        fromdate = datetime.datetime(2003, 11, 18)
    else:
        fromdate = datetime.datetime(1991, 1, 1)

    data = bt.feeds.GenericCSVData(
        dataname=datapath,
        fromdate=fromdate,
        todate=datetime.datetime(2026, 12, 31),
        dtformat='%Y-%m-%d',
        datetime=0,
        open=1,
        high=2,
        low=3,
        close=4,
        volume=5,
        openinterest=-1,
        reverse=False)
    cerebro.adddata(data)

    cerebro.broker.setcash(100000.0)
    cerebro.broker.setcommission(commission=0.001)  # 0.1% 佣金

    initial_cash = cerebro.broker.getcash()
    print(f'[初始] 资金: {initial_cash:.2f}')
    print('-' * 50)

    results = cerebro.run(maxcpus=1)
    strat = results[0]
    final_cash = cerebro.broker.getvalue()

    print('-' * 50)
    print('[回测结果] 1995-01-03 至 2014-12-31')
    print('-' * 50)

    # 收益分析
    ret = strat.analyzers.returns.get_analysis()
    total_return = ret['rnorm100'] / 100 * (2014 - 1995 + 1)  # 近似
    print(f'总收益:  {final_cash - initial_cash:,.2f}')
    print(f'收益率:  {(final_cash - initial_cash) / initial_cash:.2%}')
    print(f'年化收益率: {ret["rnorm100"]:.2f}%')

    # 夏普比率
    sharpe = strat.analyzers.sharpe.get_analysis()
    if 'sharperatio' in sharpe and sharpe['sharperatio'] is not None:
        print(f'夏普比率: {sharpe["sharperatio"]:.2f}')
    else:
        print(f'夏普比率: N/A')

    # 最大回撤
    dd = strat.analyzers.drawdown.get_analysis()
    print(f'最大回撤: {dd["max"]["drawdown"]:.2f}%')
    print(f'最大回撤金额: {dd["max"]["moneydown"]:.2f}')
    print(f'最大回撤持续天数: {dd["max"]["len"]}')

    # 交易统计
    trade = strat.analyzers.trades.get_analysis()
    if 'total' in trade and 'total' in trade['total']:
        total_trades = trade['total']['total']
        print(f'\n交易统计:')
        print(f'总交易次数: {total_trades}')
        if 'won' in trade:
            won = trade['won']['total']
            lost = trade['lost']['total'] if 'lost' in trade else 0
            if total_trades > 0:
                print(f'胜率: {won / total_trades:.2%} ({won}胜 / {lost}负)')
        if 'pnl' in trade['total']:
            print(f'总净利润: {trade["total"]["pnl"]:.2f}')
        if 'pnl' in trade and 'average' in trade['pnl']:
            print(f'平均每笔盈亏: {trade["pnl"]["average"]:.2f}')
        if 'won' in trade and 'pnl' in trade['won'] and 'max' in trade['won']['pnl']:
            print(f'最大单笔盈利: {trade["won"]["pnl"]["max"]:.2f}')
        if 'lost' in trade and 'pnl' in trade['lost'] and 'max' in trade['lost']['pnl']:
            print(f'最大单笔亏损: {trade["lost"]["pnl"]["max"]:.2f}')

    print('-' * 50)
    print(f'[最终] 资金: {final_cash:.2f}')

    # 收集回测结果，通过微信发送
    msg_lines = [
        '📊 回测结果: 1995-01-03 至 2014-12-31',
        '',
        f'初始资金: {initial_cash:.2f}',
        f'最终资金: {final_cash:.2f}',
        f'总收益: {final_cash - initial_cash:,.2f}',
        f'收益率: {(final_cash - initial_cash) / initial_cash:.2%}',
        f'年化收益率: {ret["rnorm100"]:.2f}%',
        '',
    ]

    if 'sharperatio' in sharpe and sharpe['sharperatio'] is not None:
        msg_lines.append(f'夏普比率: {sharpe["sharperatio"]:.2f}')
    else:
        msg_lines.append(f'夏普比率: N/A')

    msg_lines.extend([
        f'最大回撤: {dd["max"]["drawdown"]:.2f}%',
        f'最大回撤金额: {dd["max"]["moneydown"]:.2f}',
        f'最大回撤持续天数: {dd["max"]["len"]}',
        '',
        f'交易统计:',
        f'总交易次数: {total_trades}',
    ])

    if 'won' in trade:
        won = trade['won']['total']
        lost = trade['lost']['total'] if 'lost' in trade else 0
        if total_trades > 0:
            msg_lines.append(f'胜率: {won / total_trades:.2%} ({won}胜 / {lost}负)')

    if 'pnl' in trade['total']:
        msg_lines.append(f'总净利润: {trade["total"]["pnl"]:.2f}')
    if 'pnl' in trade and 'average' in trade['pnl']:
        msg_lines.append(f'平均每笔盈亏: {trade["pnl"]["average"]:.2f}')
    if 'won' in trade and 'pnl' in trade['won'] and 'max' in trade['won']['pnl']:
        msg_lines.append(f'最大单笔盈利: {trade["won"]["pnl"]["max"]:.2f}')
    if 'lost' in trade and 'pnl' in trade['lost'] and 'max' in trade['lost']['pnl']:
        msg_lines.append(f'最大单笔亏损: {trade["lost"]["pnl"]["max"]:.2f}')

    # 发送到微信
    msg = '\n\n'.join(msg_lines)
    notifier.send(f'[{strategy_name}] 回测结果：{datapath}', msg)

    # 绘制图表
    if args.plot:
        cerebro.plot(style='candlestick')


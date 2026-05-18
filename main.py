import datetime
import os
import argparse
import backtrader as bt
import backtrader.analyzers as btanalyzers

from notifier import create_notifier
from ai import MultiPeriodTrendStrategy as TrendFollowStrategy

parser = argparse.ArgumentParser(description="回测系统")
parser.add_argument(
    "--plot", 
    action="store_true", 
    help="开启调试模式（写--plot则为True，不写则为False）"
)
args = parser.parse_args()

# 创建通知器（如果配置了 Server酱 则使用，否则使用控制台）
notifier = create_notifier(os.getenv("WECHAT_SEND_KEY", ""))
# notifier.send("回测结果", "测试消息\n\n第二行")

if __name__ == '__main__':
    cerebro = bt.Cerebro()
    cerebro.addstrategy(TrendFollowStrategy)

    # 添加分析器
    cerebro.addanalyzer(btanalyzers.Returns, _name='returns')
    cerebro.addanalyzer(btanalyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(btanalyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(btanalyzers.SharpeRatio, _name='sharpe', timeframe=bt.TimeFrame.Years)

    datapath = './orcl-1995-2014.txt'

    data = bt.feeds.YahooFinanceCSVData(
        dataname=datapath,
        fromdate=datetime.datetime(1995, 1, 3),
        todate=datetime.datetime(2014, 12, 31),
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
    notifier.send( f'回测结果：{datapath}', msg)

    # 绘制图表
    if args.plot:
        cerebro.plot(style='candlestick')


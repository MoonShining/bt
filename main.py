import datetime
import os
import backtrader as bt

from notifier import create_notifier
from rsi_strategy import RSIStrategy
from ai import MultiPeriodTrendStrategy as TrendFollowStrategy

# 创建通知器（如果配置了 Server酱 则使用，否则使用控制台）
notifier = create_notifier(os.getenv("WECHAT_SEND_KEY", ""))
# notifier.send("回测结果", "测试消息\n\n第二行")

if __name__ == '__main__':
    cerebro = bt.Cerebro()
    cerebro.addstrategy(TrendFollowStrategy)

    datapath = './orcl-1995-2014.txt'

    data = bt.feeds.YahooFinanceCSVData(
        dataname=datapath,
        fromdate=datetime.datetime(2000, 1, 1),
        todate=datetime.datetime(2000, 12, 31),
        reverse=False)
    cerebro.adddata(data)

    cerebro.broker.setcash(100000.0)
    cerebro.broker.setcommission(commission=0.0)

    initial_cash = cerebro.broker.getcash()
    cerebro.run(maxcpus=1)
    # 绘制图表
    cerebro.plot(style='candle')


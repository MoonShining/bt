import datetime
import backtrader as bt


# 定义极简锤子线策略
class SimpleHammerBuyStrategy(bt.Strategy):
    params = (
        ('printlog', True),  # 是否打印日志
    )

    def __init__(self):
        # 1. 保存K线数据引用（TA-Lib需要open/high/low/close）
        self.open = self.data.open
        self.high = self.data.high
        self.low = self.data.low
        self.close = self.data.close

        # 2. TA-Lib识别锤子线（核心）
        self.hammer_signal = bt.talib.CDLHAMMER(
            self.open, self.high, self.low, self.close
        )

    def next(self):
        # --------------- 步骤1：识别锤子线 ---------------
        # 当前K线是锤子线（TA-Lib返回100）
        if self.hammer_signal[0] == 100:
            self.buy(exectype=bt.Order.Market)
            if self.params.printlog:
                self.log(f"识别到锤子线 | 价格：{self.close[0]:.2f}")
            return

    def log(self, txt, dt=None):
        """日志打印函数"""
        dt = dt or self.datas[0].datetime.date(0)
        print(f"{dt.isoformat()} - {txt}")


if __name__ == '__main__':
    cerebro = bt.Cerebro()
    cerebro.addstrategy(SimpleHammerBuyStrategy)

    datapath1 = './orcl-1995-2014.txt'
    data1 = bt.feeds.YahooFinanceCSVData(
        dataname=datapath1,
        fromdate=datetime.datetime(2000, 1, 1),
        todate=datetime.datetime(2000, 12, 31),
        reverse=False)
    cerebro.adddata(data1, name='ORCL')

    cerebro.broker.setcash(100000.0)
    cerebro.broker.setcommission(commission=0.0)

    cerebro.run(maxcpus=1)
    cerebro.plot(style='candlestick')
    print(cerebro.broker.getvalue())

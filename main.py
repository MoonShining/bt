import backtrader as bt

class TestStrategy(bt.Strategy):
    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        print('%s, %s' % (dt.isoformat(), txt))

    def __init__(self):
        self.dataclose = self.datas[0].close
        self.order = None

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log('BUY EXECUTED, %.2f' % order.executed.price)
            elif order.issell():
                self.log('SELL EXECUTED, %.2f' % order.executed.price)

            self.bar_executed = len(self)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('Order Canceled/Margin/Rejected')

        self.order = None

    def next(self):
        self.log('Close, %.2f' % self.dataclose[0])

        if self.order:
            return

        if not self.position:
            if self.dataclose[0] < self.dataclose[-1]:
                if self.dataclose[-1] < self.dataclose[-2]:
                    self.log('BUY CREATE, %.2f' % self.dataclose[0])
                    self.order = self.buy()
        else:
            if len(self) >= (self.bar_executed + 5):
                self.log('SELL CREATE, %.2f' % self.dataclose[0])
                self.order = self.sell()


def main():
    cerebro = bt.Cerebro()

    # 设置初始资金为 100000.0
    cerebro.broker.setcash(100000.0)
    # 设置交易佣金为千分之三（0.1%）
    cerebro.broker.setcommission(commission=0.001)
    # 滑点 0.1%
    cerebro.broker.set_slippage_perc(0.001)
    
    print(f'初始资金: {cerebro.broker.getvalue():.2f}')

    data = bt.feeds.GenericCSVData(
        dataname="./orcl-1995-2014.txt", dtformat="%Y-%m-%d",
    )
    cerebro.adddata(data)
    cerebro.addstrategy(TestStrategy)

    cerebro.run()
    cerebro.plot()

    print(f'最终资金: {cerebro.broker.getvalue():.2f}')

if __name__ == '__main__':
    main()
import backtrader as bt
import backtrader.indicators as btind

# 定义RSI趋势策略
class RSIStrategy(bt.Strategy):
    params = (
        ('rsi_period', 5),
        ('rsi_low', 45),
        ('rsi_high', 65),
        ('stop_loss_pct', 0.15),
        ('take_profit_pct', 0.100)
    )

    def __init__(self):
        self.rsi = btind.RSI(self.data, period=self.params.rsi_period)
        self.order = None
        self.stop_loss_price = 0
        self.take_profit_price = 0

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        self.order = None

    def next(self):
        if len(self.data) < self.params.rsi_period + 1:
            return

        if not self.position:
            if self.rsi[-1] < self.params.rsi_low:
                cash = self.broker.getcash()
                size = int(cash / self.data.close[-1])
                if size > 0:
                    self.order = self.buy(size=size)
                    self.stop_loss_price = self.data.close[-1] * (1 - self.params.stop_loss_pct)
                    self.take_profit_price = self.data.close[-1] * (1 + self.params.take_profit_pct)
        else:
            if self.position.size > 0:
                if (self.data.close[-1] <= self.stop_loss_price or
                    self.data.close[-1] >= self.take_profit_price or
                    self.rsi[-1] > self.params.rsi_high):
                    self.close()
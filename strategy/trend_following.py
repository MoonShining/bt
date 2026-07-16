import backtrader as bt


class TrendFollowingStrategy(bt.Strategy):
    params = (
        ("fast_period", 20),
        ("slow_period", 120),
        ("cash_buffer", 0.95),
    )

    def __init__(self):
        self.orders = {}
        self.fast_averages = {}
        self.slow_averages = {}
        for data in self.datas:
            self.orders[data] = None
            self.fast_averages[data] = bt.indicators.SimpleMovingAverage(
                data.close,
                period=self.p.fast_period,
            )
            self.slow_averages[data] = bt.indicators.SimpleMovingAverage(
                data.close,
                period=self.p.slow_period,
            )

    def notify_order(self, order):
        if order.status in (order.Completed, order.Canceled, order.Margin, order.Rejected):
            self.orders[order.data] = None

    def next(self):
        if any(order is not None for order in self.orders.values()):
            return
        if any(len(data) < self.p.slow_period for data in self.datas):
            return

        selected = self._select_data()
        for data in self.datas:
            position = self.getposition(data)
            if position and data is not selected:
                self.orders[data] = self.close(data=data)

        if selected is None or self.getposition(selected):
            return

        cash = self.broker.getcash() * self.p.cash_buffer
        price = selected.close[0]
        if price <= 0:
            return

        size = int(cash / price)
        if size > 0:
            self.orders[selected] = self.buy(data=selected, size=size)

    def _select_data(self):
        candidates = []
        for data in self.datas:
            fast_average = self.fast_averages[data][0]
            slow_average = self.slow_averages[data][0]
            if data.close[0] > slow_average and fast_average > slow_average:
                candidates.append((data.close[0] / slow_average - 1, data))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

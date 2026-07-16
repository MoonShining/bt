import backtrader as bt


class MeanReversionStrategy(bt.Strategy):
    params = (
        ("period", 20),
        ("entry_deviation", -0.06),
        ("exit_deviation", -0.01),
        ("cash_buffer", 0.95),
    )

    def __init__(self):
        self.orders = {}
        self.averages = {}
        for data in self.datas:
            self.orders[data] = None
            self.averages[data] = bt.indicators.SimpleMovingAverage(
                data.close,
                period=self.p.period,
            )

    def notify_order(self, order):
        if order.status in (order.Completed, order.Canceled, order.Margin, order.Rejected):
            self.orders[order.data] = None

    def next(self):
        if any(order is not None for order in self.orders.values()):
            return
        if any(len(data) < self.p.period for data in self.datas):
            return

        selected = self._select_data()
        for data in self.datas:
            position = self.getposition(data)
            if not position:
                continue
            deviation = self._deviation(data)
            if data is not selected or deviation >= self.p.exit_deviation:
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
            deviation = self._deviation(data)
            if deviation <= self.p.entry_deviation:
                candidates.append((deviation, data))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def _deviation(self, data):
        average = self.averages[data][0]
        if average <= 0:
            return 0.0
        return data.close[0] / average - 1

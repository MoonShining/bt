import backtrader as bt


class DualMomentumRotationStrategy(bt.Strategy):
    params = (
        ("momentum_period", 60),
        ("rebalance_period", 20),
        ("min_momentum", 0.0),
        ("cash_buffer", 0.95),
    )

    def __init__(self):
        self.orders = {}
        self.bar_count = 0
        for data in self.datas:
            self.orders[data] = None

    def notify_order(self, order):
        if order.status in (order.Completed, order.Canceled, order.Margin, order.Rejected):
            self.orders[order.data] = None

    def next(self):
        if any(order is not None for order in self.orders.values()):
            return

        self.bar_count += 1
        if self.bar_count % self.p.rebalance_period != 0:
            return
        if any(len(data) <= self.p.momentum_period for data in self.datas):
            return

        selected = self._select_data()
        for data in self.datas:
            position = self.getposition(data)
            if position and data is not selected:
                self.orders[data] = self.close(data=data)

        if selected is None:
            return
        if self.getposition(selected):
            return

        cash = self.broker.getcash() * self.p.cash_buffer
        price = selected.close[0]
        if price <= 0:
            return

        size = int(cash / price)
        if size > 0:
            self.orders[selected] = self.buy(data=selected, size=size)

    def _select_data(self):
        ranked = []
        for data in self.datas:
            past_close = data.close[-self.p.momentum_period]
            current_close = data.close[0]
            if past_close <= 0:
                continue

            momentum = current_close / past_close - 1
            if momentum > self.p.min_momentum:
                ranked.append((momentum, data))

        if not ranked:
            return None

        ranked.sort(key=lambda item: item[0], reverse=True)
        return ranked[0][1]

import backtrader as bt


class TrendFollowingStrategy(bt.Strategy):
    params = (
        ("fast_period", 14),
        ("slow_period", 30),
        ("atr_period", 14),
        ("atr_multiplier", 3.0),
        ("cash_buffer", 0.95),
    )

    def __init__(self):
        self.orders = {}
        self.order_events = []
        self.fast_averages = {}
        self.slow_averages = {}
        self.atr_indicators = {}
        self.entry_prices = {}
        self.stop_prices = {}
        self.highest_closes = {}
        for data in self.datas:
            self.orders[data] = None
            self.entry_prices[data] = None
            self.stop_prices[data] = None
            self.highest_closes[data] = None
            self.fast_averages[data] = bt.indicators.SimpleMovingAverage(
                data.close,
                period=self.p.fast_period,
            )
            self.slow_averages[data] = bt.indicators.SimpleMovingAverage(
                data.close,
                period=self.p.slow_period,
            )
            self.atr_indicators[data] = bt.indicators.AverageTrueRange(
                data,
                period=self.p.atr_period,
            )

    def notify_order(self, order):
        if order.status == order.Completed:
            side = "buy" if order.isbuy() else "sell"
            self.order_events.append(
                {
                    "side": side,
                    "size": abs(int(order.executed.size)),
                    "price": float(order.executed.price),
                }
            )
            if order.isbuy():
                self.entry_prices[order.data] = float(order.executed.price)
                self.highest_closes[order.data] = float(order.data.close[0])
                self._update_stop(order.data)
            elif not self.getposition(order.data):
                self._reset_position_state(order.data)

        if order.status in (order.Completed, order.Canceled, order.Margin, order.Rejected):
            self.orders[order.data] = None

    def next(self):
        if any(order is not None for order in self.orders.values()):
            return
        if any(len(data) < self.p.slow_period for data in self.datas):
            return

        for data in self.datas:
            position = self.getposition(data)
            if self._protect_long_only_position(data, position):
                return
            if position.size > 0:
                self._update_stop(data)
                stop_price = self.stop_prices[data]
                if stop_price is not None and data.close[0] <= stop_price:
                    self.orders[data] = self.close(data=data)
                    return

        for data in self.datas:
            position = self.getposition(data)
            if position.size > 0:
                return

        selected = self._select_data()
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

    def _update_stop(self, data):
        atr = float(self.atr_indicators[data][0])
        if atr <= 0:
            return

        current_close = float(data.close[0])
        highest_close = self.highest_closes[data]
        if highest_close is None or current_close > highest_close:
            highest_close = current_close
            self.highest_closes[data] = highest_close

        candidate_stop = highest_close - self.p.atr_multiplier * atr
        current_stop = self.stop_prices[data]
        if current_stop is None or candidate_stop > current_stop:
            self.stop_prices[data] = candidate_stop

    def _protect_long_only_position(self, data, position):
        if position.size < 0:
            self.orders[data] = self.close(data=data)
            return True
        return False

    def _reset_position_state(self, data):
        self.entry_prices[data] = None
        self.stop_prices[data] = None
        self.highest_closes[data] = None

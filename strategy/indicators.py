import math

import backtrader as bt
import numpy as np


class RSRSIndicator(bt.Indicator):
    lines = ("rsrs", "r2", "adjusted_rsrs", "zscore")
    params = (
        ("regression_period", 18),
        ("standardization_period", 600),
    )

    def __init__(self):
        if self.p.regression_period < 2:
            raise ValueError("regression_period 必须至少为 2")
        if self.p.standardization_period < 2:
            raise ValueError("standardization_period 必须至少为 2")

        self.addminperiod(self.p.regression_period)
        self._adjusted_history = []

    def next(self):
        lows = [float(value) for value in self.data.low.get(size=self.p.regression_period)]
        highs = [float(value) for value in self.data.high.get(size=self.p.regression_period)]

        slope, _, r2 = linear_regression(lows, highs)
        adjusted_rsrs = slope * r2
        self._adjusted_history.append(adjusted_rsrs)

        self.lines.rsrs[0] = slope
        self.lines.r2[0] = r2
        self.lines.adjusted_rsrs[0] = adjusted_rsrs
        self.lines.zscore[0] = self._zscore(adjusted_rsrs)

    def _zscore(self, current_value):
        if len(self._adjusted_history) < self.p.standardization_period:
            return math.nan

        window = self._adjusted_history[-self.p.standardization_period :]
        mean = sum(window) / len(window)
        variance = sum((value - mean) ** 2 for value in window) / len(window)
        stddev = math.sqrt(variance)
        if stddev == 0:
            return math.nan
        return (current_value - mean) / stddev


class SlopeMomentumIndicator(bt.Indicator):
    lines = ("slope", "annualized_return", "r2", "score")
    params = (
        ("period", 60),
        ("use_weighted_regression", False),
        ("trading_days", 250),
    )

    def __init__(self):
        if self.p.period < 2:
            raise ValueError("period 必须至少为 2")
        if self.p.trading_days <= 0:
            raise ValueError("trading_days 必须大于 0")

        self.addminperiod(self.p.period)

    def next(self):
        closes = [float(value) for value in self.data.close.get(size=self.p.period)]
        if any(close <= 0 for close in closes):
            slope = annualized_return = r2 = score = math.nan
        else:
            x_values = list(range(self.p.period))
            y_values = [math.log(close) for close in closes]
            weights = self._linear_weights() if self.p.use_weighted_regression else None
            slope, _, r2 = linear_regression(x_values, y_values, weights=weights)
            annualized_return = math.exp(slope * self.p.trading_days) - 1
            score = annualized_return * r2

        self.lines.slope[0] = slope
        self.lines.annualized_return[0] = annualized_return
        self.lines.r2[0] = r2
        self.lines.score[0] = score

    def _linear_weights(self):
        if self.p.period == 1:
            return [1.0]
        step = 1.0 / (self.p.period - 1)
        return [1.0 + index * step for index in range(self.p.period)]


def linear_regression(x_values, y_values, weights=None):
    x_array = np.asarray(x_values, dtype=float)
    y_array = np.asarray(y_values, dtype=float)
    weight_array = None if weights is None else np.asarray(weights, dtype=float)
    if np.var(x_array) == 0 or (weight_array is not None and np.sum(weight_array) == 0):
        return math.nan, math.nan, math.nan

    slope, intercept = np.polyfit(x_array, y_array, 1, w=weight_array)
    y_mean = np.average(y_array, weights=weight_array)
    y_pred = slope * x_array + intercept
    if weight_array is None:
        total_sum_squares = np.sum((y_array - y_mean) ** 2)
        residual_sum_squares = np.sum((y_array - y_pred) ** 2)
    else:
        total_sum_squares = np.sum(weight_array * (y_array - y_mean) ** 2)
        residual_sum_squares = np.sum(weight_array * (y_array - y_pred) ** 2)

    if total_sum_squares == 0:
        r2 = 1.0
    else:
        r2 = 1.0 - residual_sum_squares / total_sum_squares

    return float(slope), float(intercept), max(0.0, min(1.0, float(r2)))

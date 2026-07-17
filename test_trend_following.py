import unittest

import backtrader as bt
import pandas as pd

from strategy.trend_following import TrendFollowingStrategy


def run_strategy(bars, **params):
    dataframe = pd.DataFrame(
        bars,
        columns=["open", "high", "low", "close"],
        index=pd.date_range("2024-01-01", periods=len(bars), freq="D"),
    )
    dataframe["volume"] = 1000
    dataframe["openinterest"] = 0

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.setcash(100000)
    cerebro.broker.setcommission(commission=0.0)
    cerebro.adddata(bt.feeds.PandasData(dataname=dataframe))
    cerebro.addstrategy(TrendFollowingStrategy, **params)
    return cerebro.run()[0]


class TrendFollowingStrategyTest(unittest.TestCase):
    def test_short_position_is_closed_without_adding_short(self):
        class Position:
            size = -10

        class StrategyProbe:
            def __init__(self):
                self.orders = {}
                self.closed = []

            def close(self, data=None):
                self.closed.append(data)
                return "close-order"

        probe = StrategyProbe()

        TrendFollowingStrategy._protect_long_only_position(probe, "data", Position())

        self.assertEqual(probe.orders["data"], "close-order")
        self.assertEqual(probe.closed, ["data"])

    def test_atr_stop_closes_full_position(self):
        bars = [
            (10, 10.5, 9.5, 10),
            (10.5, 11, 10, 10.5),
            (11, 11.5, 10.5, 11),
            (11.5, 12, 11, 11.5),
            (12, 12.5, 11.5, 12),
            (12.5, 13, 12, 12.5),
            (13, 13.5, 12.5, 13),
            (13.5, 14, 13, 13.5),
            (14, 14.5, 13.5, 14),
            (14, 14.5, 9, 9.5),
            (9.5, 10, 9, 9.5),
        ]
        strategy = run_strategy(
            bars,
            fast_period=2,
            slow_period=3,
            atr_period=2,
            atr_multiplier=1.0,
            adx_period=2,
            min_adx=0.0,
            atr_entry_multiplier=0.0,
            cash_buffer=0.95,
        )

        sells = [event for event in strategy.order_events if event["side"] == "sell"]

        self.assertTrue(sells)
        self.assertEqual(strategy.getposition(strategy.datas[0]).size, 0)

    def test_trend_reversal_does_not_sell_before_trailing_stop(self):
        bars = [
            (10, 10.5, 9.5, 10),
            (11, 11.5, 10.5, 11),
            (12, 12.5, 11.5, 12),
            (13, 13.5, 12.5, 13),
            (14, 14.5, 13.5, 14),
            (13, 13.5, 12.5, 13),
            (12, 12.5, 11.5, 12),
            (11, 11.5, 10.5, 11),
        ]
        strategy = run_strategy(
            bars,
            fast_period=2,
            slow_period=3,
            atr_period=2,
            atr_multiplier=10.0,
            adx_period=2,
            min_adx=0.0,
            atr_entry_multiplier=0.0,
            cash_buffer=0.95,
        )

        sells = [event for event in strategy.order_events if event["side"] == "sell"]

        self.assertEqual(sells, [])
        self.assertGreater(strategy.getposition(strategy.datas[0]).size, 0)

    def test_trailing_take_profit_closes_after_high_water_mark_pullback(self):
        bars = [
            (10, 10.5, 9.5, 10),
            (10.5, 11, 10, 10.5),
            (11, 11.5, 10.5, 11),
            (11.5, 12, 11, 11.5),
            (12, 12.5, 11.5, 12),
            (12.5, 13, 12, 12.5),
            (13, 13.5, 12.5, 13),
            (13.5, 14, 13, 13.5),
            (14, 14.5, 13.5, 14),
            (14, 14.5, 12.8, 13.0),
            (13.0, 13.5, 12.5, 13.0),
        ]
        strategy = run_strategy(
            bars,
            fast_period=2,
            slow_period=3,
            atr_period=2,
            atr_multiplier=1.0,
            adx_period=2,
            min_adx=0.0,
            atr_entry_multiplier=0.0,
            cash_buffer=0.95,
        )

        sells = [event for event in strategy.order_events if event["side"] == "sell"]

        self.assertTrue(sells)
        self.assertEqual(strategy.getposition(strategy.datas[0]).size, 0)

    def test_low_adx_sideways_breakout_is_filtered(self):
        bars = [
            (10.00, 10.20, 9.80, 10.00),
            (10.00, 10.20, 9.80, 10.05),
            (10.05, 10.25, 9.85, 10.10),
            (10.10, 10.30, 9.90, 10.05),
            (10.05, 10.25, 9.85, 10.10),
            (10.10, 10.30, 9.90, 10.15),
            (10.15, 10.35, 9.95, 10.10),
            (10.10, 10.30, 9.90, 10.15),
            (10.15, 10.35, 9.95, 10.20),
            (10.20, 10.40, 10.00, 10.15),
            (10.15, 10.35, 9.95, 10.20),
            (10.20, 10.40, 10.00, 10.25),
        ]
        strategy = run_strategy(
            bars,
            fast_period=2,
            slow_period=3,
            atr_period=2,
            adx_period=3,
            min_adx=80.0,
            atr_entry_multiplier=0.0,
            cash_buffer=0.95,
        )

        buys = [event for event in strategy.order_events if event["side"] == "buy"]

        self.assertEqual(buys, [])

    def test_atr_stop_cooldown_prevents_immediate_reentry(self):
        bars = [
            (10, 10.5, 9.5, 10),
            (10.5, 11, 10, 10.5),
            (11, 11.5, 10.5, 11),
            (11.5, 12, 11, 11.5),
            (12, 12.5, 11.5, 12),
            (12.5, 13, 12, 12.5),
            (13, 13.5, 12.5, 13),
            (13.5, 14, 13, 13.5),
            (14, 14.5, 13.5, 14),
            (14, 14.5, 9, 9.5),
            (14.5, 15, 14, 14.5),
            (15, 15.5, 14.5, 15),
            (15.5, 16, 15, 15.5),
        ]
        strategy = run_strategy(
            bars,
            fast_period=2,
            slow_period=3,
            atr_period=2,
            atr_multiplier=1.0,
            adx_period=2,
            min_adx=0.0,
            atr_entry_multiplier=0.0,
            cooldown_period=3,
            cash_buffer=0.95,
        )

        buys = [event for event in strategy.order_events if event["side"] == "buy"]
        sells = [event for event in strategy.order_events if event["side"] == "sell"]

        self.assertEqual(len(sells), 1)
        self.assertEqual(len(buys), 1)


if __name__ == "__main__":
    unittest.main()

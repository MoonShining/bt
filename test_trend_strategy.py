import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from ai import MultiPeriodTrendStrategy


class TrendStrategyStateTest(unittest.TestCase):
    def test_stop_loss_sets_bar_exit_guard(self):
        strategy = MultiPeriodTrendStrategy.__new__(MultiPeriodTrendStrategy)
        strategy.avg_entry_price = 10.0
        strategy.sl_price = 9.5
        strategy.order = None
        strategy.exited_this_bar = False
        strategy.p = SimpleNamespace(use_trailing_stop=False, entry_mode="pullback")
        strategy.data = SimpleNamespace(close=[9.4])

        closed = []
        strategy.close = lambda: closed.append("close")
        strategy.log = lambda _: None

        with patch.object(MultiPeriodTrendStrategy, "position", new_callable=PropertyMock) as position:
            position.return_value = SimpleNamespace(size=100)
            MultiPeriodTrendStrategy._check_stop_loss(strategy)

        self.assertEqual(closed, ["close"])
        self.assertTrue(strategy.exited_this_bar)

    def test_closed_order_resets_state_and_keeps_exit_guard(self):
        strategy = MultiPeriodTrendStrategy.__new__(MultiPeriodTrendStrategy)
        strategy.total_shares = 100
        strategy.exited_this_bar = True
        strategy._reset_state = lambda: setattr(strategy, "state_reset", True)
        strategy.log = lambda _: None

        order = SimpleNamespace(
            Submitted=1,
            Accepted=2,
            Completed=3,
            Canceled=4,
            Rejected=5,
            Margin=6,
            status=3,
            isbuy=lambda: False,
            executed=SimpleNamespace(price=9.4, size=-100),
        )

        MultiPeriodTrendStrategy.notify_order(strategy, order)

        self.assertTrue(strategy.state_reset)
        self.assertTrue(strategy.exited_this_bar)
        self.assertIsNone(strategy.order)

    def test_trend_hold_entry_uses_ma_slope_without_rsi_or_volume(self):
        strategy = MultiPeriodTrendStrategy.__new__(MultiPeriodTrendStrategy)
        strategy.p = SimpleNamespace(
            entry_mode="trend_hold",
            hold_entry_ma=100,
            hold_ma_slope_lookback=30,
            enable_us10y_filter=False,
            max_single_position=0.95,
            min_bars_between_add=8,
        )
        strategy.broker = SimpleNamespace(getvalue=lambda: 100000)
        strategy.data = SimpleNamespace(close=[12.0])
        strategy.hold_entry_ma = {0: 10.0, -30: 9.5}
        strategy._is_us10y_allowed = lambda: True
        strategy.__len__ = lambda: 200
        strategy.last_exit_bar = None

        with patch.object(MultiPeriodTrendStrategy, "position", new_callable=PropertyMock) as position:
            with patch.object(MultiPeriodTrendStrategy, "__len__", lambda _: 200):
                position.return_value = SimpleNamespace(size=0)
                self.assertTrue(MultiPeriodTrendStrategy._check_long_signal(strategy))

    def test_trend_hold_respects_reentry_cooldown(self):
        strategy = MultiPeriodTrendStrategy.__new__(MultiPeriodTrendStrategy)
        strategy.p = SimpleNamespace(
            entry_mode="trend_hold",
            hold_entry_ma=100,
            hold_ma_slope_lookback=30,
            enable_us10y_filter=False,
            max_single_position=0.95,
            min_bars_between_add=8,
            reentry_cooldown_bars=20,
        )
        strategy.broker = SimpleNamespace(getvalue=lambda: 100000)
        strategy.data = SimpleNamespace(close=[12.0])
        strategy.hold_entry_ma = {0: 10.0, -30: 9.5}
        strategy._is_us10y_allowed = lambda: True
        strategy.last_exit_bar = 190

        with patch.object(MultiPeriodTrendStrategy, "position", new_callable=PropertyMock) as position:
            with patch.object(MultiPeriodTrendStrategy, "__len__", lambda _: 200):
                position.return_value = SimpleNamespace(size=0)
                self.assertFalse(MultiPeriodTrendStrategy._check_long_signal(strategy))

    def test_trend_hold_does_not_pyramid(self):
        strategy = MultiPeriodTrendStrategy.__new__(MultiPeriodTrendStrategy)
        strategy.p = SimpleNamespace(
            entry_mode="trend_hold",
            max_single_position=0.95,
            min_bars_between_add=8,
        )
        strategy.broker = SimpleNamespace(getvalue=lambda: 100000)
        strategy.data = SimpleNamespace(close=[12.0])

        with patch.object(MultiPeriodTrendStrategy, "position", new_callable=PropertyMock) as position:
            position.return_value = SimpleNamespace(size=100)
            self.assertFalse(MultiPeriodTrendStrategy._check_long_signal(strategy))


class BacktestDateRangeTest(unittest.TestCase):
    def test_effective_date_range_uses_available_csv_data(self):
        from main import resolve_effective_date_range

        requested_from = date(2025, 1, 1)
        requested_to = date(2026, 12, 31)

        effective_from, effective_to = resolve_effective_date_range(
            "sh000001_daily.csv",
            requested_from,
            requested_to,
        )

        self.assertEqual(effective_from, date(2025, 1, 2))
        self.assertEqual(effective_to, date(2026, 5, 18))


if __name__ == "__main__":
    unittest.main()

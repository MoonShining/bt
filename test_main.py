import datetime as dt
import unittest
from pathlib import Path

import pandas as pd

from main import BacktestConfig, build_parser, fetch_funds_to_csv, run_backtest, write_backtrader_csv


class FakeClient:
    def __init__(self):
        self.calls = []

    def fetch_daily_bars(self, symbol, start_date, end_date, adjust=None):
        self.calls.append((symbol, start_date, end_date, adjust))
        dates = pd.date_range(start_date, periods=40, freq="D")
        return pd.DataFrame(
            {
                "open": range(10, 50),
                "high": range(11, 51),
                "low": range(9, 49),
                "close": range(10, 50),
                "volume": [1000] * 40,
                "openinterest": [0] * 40,
            },
            index=dates,
        )


class MainTest(unittest.TestCase):
    def test_fetch_funds_to_csv_fetches_each_symbol_and_writes_backtrader_csv(self):
        with _tmpdir() as tmp_path:
            client = FakeClient()
            start = dt.date(2024, 1, 1)
            end = dt.date(2024, 2, 29)

            paths = fetch_funds_to_csv(
                symbols=["000001", "000002"],
                start_date=start,
                end_date=end,
                output_dir=tmp_path,
                client=client,
                adjust="qfq",
            )

            self.assertEqual([path.name for path in paths], ["000001_daily.csv", "000002_daily.csv"])
            self.assertEqual(
                client.calls,
                [
                    ("000001", start, end, "qfq"),
                    ("000002", start, end, "qfq"),
                ],
            )

            csv_text = (tmp_path / "000001_daily.csv").read_text()
            self.assertEqual(csv_text.splitlines()[0], "date,open,high,low,close,volume,openinterest")
            self.assertIn("2024-01-01,10,11,9,10,1000,0", csv_text)

    def test_run_backtest_loads_csv_files_and_returns_summary(self):
        with _tmpdir() as tmp_path:
            dataframe = pd.DataFrame(
                {
                    "date": pd.date_range("2024-01-01", periods=80, freq="D"),
                    "open": range(10, 90),
                    "high": range(11, 91),
                    "low": range(9, 89),
                    "close": range(10, 90),
                    "volume": [1000] * 80,
                    "openinterest": [0] * 80,
                }
            )
            csv_path = tmp_path / "000001_daily.csv"
            dataframe.to_csv(csv_path, index=False)

            result = run_backtest(
                csv_paths=[csv_path],
                config=BacktestConfig(
                    cash=100000,
                    commission=0.001,
                    momentum_period=20,
                    rebalance_period=5,
                    min_momentum=0.0,
                ),
            )

            self.assertEqual(result.symbols, ["000001"])
            self.assertEqual(result.start_value, 100000)
            self.assertGreater(result.end_value, 0)
            self.assertGreater(result.total_return, -1)
            self.assertIsInstance(result.max_drawdown, float)

    def test_write_backtrader_csv_handles_date_named_index(self):
        with _tmpdir() as tmp_path:
            dates = pd.date_range("2024-01-01", periods=3, freq="D")
            dates.name = "date"
            dataframe = pd.DataFrame(
                {
                    "open": [1, 2, 3],
                    "high": [2, 3, 4],
                    "low": [0.5, 1.5, 2.5],
                    "close": [1.5, 2.5, 3.5],
                    "volume": [100, 200, 300],
                    "openinterest": [0, 0, 0],
                },
                index=dates,
            )
            csv_path = tmp_path / "161226_daily.csv"

            write_backtrader_csv(dataframe, csv_path)

            csv_text = csv_path.read_text()
            self.assertEqual(csv_text.splitlines()[0], "date,open,high,low,close,volume,openinterest")
            self.assertIn("2024-01-01,1,2,0.5,1.5,100,0", csv_text)

    def test_parser_exposes_rotation_parameters_only(self):
        parser = build_parser()

        args = parser.parse_args(
            [
                "--symbols",
                "161226,513100",
                "--start",
                "2024-01-01",
                "--end",
                "2024-12-31",
                "--momentum-period",
                "90",
                "--rebalance-period",
                "15",
                "--min-momentum",
                "0.02",
            ]
        )

        self.assertEqual(args.momentum_period, 90)
        self.assertEqual(args.rebalance_period, 15)
        self.assertEqual(args.min_momentum, 0.02)
        self.assertFalse(hasattr(args, "stake"))
        self.assertFalse(hasattr(args, "fast_period"))
        self.assertFalse(hasattr(args, "slow_period"))

    def test_dual_momentum_rotates_into_strongest_positive_etf(self):
        with _tmpdir() as tmp_path:
            weak_path = tmp_path / "weak_daily.csv"
            strong_path = tmp_path / "strong_daily.csv"
            _write_price_csv(weak_path, [10.0] * 80)
            _write_price_csv(strong_path, [10.0 + index * 0.2 for index in range(80)])

            result = run_backtest(
                csv_paths=[weak_path, strong_path],
                config=BacktestConfig(
                    cash=100000,
                    commission=0.0,
                    momentum_period=20,
                    rebalance_period=5,
                    min_momentum=0.0,
                ),
            )

            self.assertEqual(result.symbols, ["weak", "strong"])
            self.assertGreater(result.end_value, result.start_value)

    def test_dual_momentum_stays_in_cash_when_no_etf_has_positive_momentum(self):
        with _tmpdir() as tmp_path:
            first_path = tmp_path / "first_daily.csv"
            second_path = tmp_path / "second_daily.csv"
            _write_price_csv(first_path, [10.0 - index * 0.02 for index in range(80)])
            _write_price_csv(second_path, [20.0 - index * 0.03 for index in range(80)])

            result = run_backtest(
                csv_paths=[first_path, second_path],
                config=BacktestConfig(
                    cash=100000,
                    commission=0.0,
                    momentum_period=20,
                    rebalance_period=5,
                    min_momentum=0.0,
                ),
            )

            self.assertEqual(result.start_value, 100000)
            self.assertEqual(result.end_value, 100000)
            self.assertEqual(result.total_return, 0.0)


class _tmpdir:
    def __enter__(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        return Path(self._tmp.name)

    def __exit__(self, exc_type, exc, tb):
        self._tmp.cleanup()


def _write_price_csv(path: Path, prices: list[float]) -> None:
    dataframe = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=len(prices), freq="D"),
            "open": prices,
            "high": [price + 0.1 for price in prices],
            "low": [price - 0.1 for price in prices],
            "close": prices,
            "volume": [1000] * len(prices),
            "openinterest": [0] * len(prices),
        }
    )
    dataframe.to_csv(path, index=False)


if __name__ == "__main__":
    unittest.main()

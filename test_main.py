import unittest

from main import BacktestConfig, build_parser


class StrategyCliTest(unittest.TestCase):
    def test_cli_selects_strategy_without_strategy_parameters(self):
        parser = build_parser()

        option_strings = {
            option
            for action in parser._actions
            for option in action.option_strings
        }
        args = parser.parse_args(
            [
                "--symbols",
                "513030",
                "--start",
                "2024-01-02",
                "--end",
                "2024-12-31",
                "--strategy",
                "dual_momentum_rotation",
            ]
        )

        self.assertEqual(args.strategy, "dual_momentum_rotation")
        self.assertNotIn("--momentum-period", option_strings)
        self.assertNotIn("--rebalance-period", option_strings)
        self.assertNotIn("--min-momentum", option_strings)

    def test_backtest_config_keeps_strategy_name_not_strategy_parameters(self):
        config = BacktestConfig(strategy="dual_momentum_rotation")

        self.assertEqual(config.strategy, "dual_momentum_rotation")
        self.assertFalse(hasattr(config, "momentum_period"))
        self.assertFalse(hasattr(config, "rebalance_period"))
        self.assertFalse(hasattr(config, "min_momentum"))


if __name__ == "__main__":
    unittest.main()

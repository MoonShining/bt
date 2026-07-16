import argparse
import datetime as dt
import html
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

import backtrader as bt
import pandas as pd

from cifangquant import CifangQuantClient
from strategy import STRATEGIES, get_strategy


DEFAULT_OUTPUT_DIR = Path("data")


@dataclass(frozen=True)
class BacktestConfig:
    cash: float = 100000.0
    commission: float = 0.001
    strategy: str = "dual_momentum_rotation"


@dataclass(frozen=True)
class BacktestResult:
    symbols: list[str]
    start_value: float
    end_value: float
    total_return: float
    max_drawdown: float
    equity_curve: list[dict[str, float | str]]


class PortfolioValueAnalyzer(bt.Analyzer):
    def start(self):
        self.values = []

    def next(self):
        data_datetime = self.strategy.datas[0].datetime
        self.values.append(
            {
                "date": bt.num2date(data_datetime[0]).date().isoformat(),
                "value": float(self.strategy.broker.getvalue()),
            }
        )

    def get_analysis(self):
        return self.values


def parse_date(value: str) -> dt.date:
    try:
        return dt.datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"日期格式应为 YYYY-MM-DD: {value}") from exc


def parse_symbols(value: str) -> list[str]:
    symbols = [item.strip() for item in value.split(",") if item.strip()]
    if not symbols:
        raise argparse.ArgumentTypeError("至少需要一个基金代码")
    return symbols


def fetch_funds_to_csv(
    symbols: Sequence[str],
    start_date: dt.date,
    end_date: dt.date,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    client: Optional[CifangQuantClient] = None,
    adjust: Optional[str] = None,
    force: bool = False,
) -> list[Path]:
    if start_date > end_date:
        raise ValueError("开始日期不能晚于结束日期")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    api_client = client or CifangQuantClient()

    csv_paths = []
    for symbol in symbols:
        csv_path = output_path / f"{symbol}_daily.csv"
        if csv_path.exists() and not force:
            csv_paths.append(csv_path)
            continue

        dataframe = api_client.fetch_daily_bars(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
        )
        write_backtrader_csv(dataframe, csv_path)
        csv_paths.append(csv_path)

    return csv_paths


def write_backtrader_csv(dataframe: pd.DataFrame, csv_path: Path) -> None:
    if dataframe.empty:
        raise ValueError(f"{csv_path.stem} 没有可写入的行情数据")

    output = dataframe.copy()
    output.index.name = None
    if "date" in output.columns:
        output["date"] = pd.to_datetime(output["date"])
    else:
        output.insert(0, "date", pd.to_datetime(output.index))

    required_columns = ["date", "open", "high", "low", "close", "volume", "openinterest"]
    if "openinterest" not in output.columns:
        output["openinterest"] = 0

    missing = [column for column in required_columns if column not in output.columns]
    if missing:
        raise ValueError(f"行情数据缺少字段: {', '.join(missing)}")

    output = output[required_columns].sort_values("date")
    output["date"] = output["date"].dt.strftime("%Y-%m-%d")
    output.to_csv(csv_path, index=False)


def run_backtest(csv_paths: Sequence[Path | str], config: BacktestConfig) -> BacktestResult:
    if not csv_paths:
        raise ValueError("没有可回测的 CSV 文件")

    cerebro = bt.Cerebro()
    cerebro.broker.setcash(config.cash)
    cerebro.broker.setcommission(commission=config.commission)
    cerebro.addstrategy(get_strategy(config.strategy))
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(PortfolioValueAnalyzer, _name="portfolio_value")

    symbols = []
    for csv_path in csv_paths:
        path = Path(csv_path)
        symbol = path.name.removesuffix("_daily.csv")
        symbols.append(symbol)
        data = bt.feeds.GenericCSVData(
            dataname=str(path),
            dtformat="%Y-%m-%d",
            datetime=0,
            open=1,
            high=2,
            low=3,
            close=4,
            volume=5,
            openinterest=6,
            headers=True,
            name=symbol,
        )
        cerebro.adddata(data)

    start_value = cerebro.broker.getvalue()
    strategies = cerebro.run()
    end_value = cerebro.broker.getvalue()
    drawdown = strategies[0].analyzers.drawdown.get_analysis()
    equity_curve = strategies[0].analyzers.portfolio_value.get_analysis()
    cerebro.plot()

    return BacktestResult(
        symbols=symbols,
        start_value=start_value,
        end_value=end_value,
        total_return=(end_value - start_value) / start_value,
        max_drawdown=float(drawdown.max.drawdown or 0.0),
        equity_curve=equity_curve,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="拉取基金历史行情 CSV 并使用 Backtrader 回测")
    parser.add_argument("--symbols", required=True, type=parse_symbols, help="基金代码，多个代码用逗号分隔")
    parser.add_argument("--start", required=True, type=parse_date, help="回测开始日期，格式 YYYY-MM-DD")
    parser.add_argument("--end", required=True, type=parse_date, help="回测结束日期，格式 YYYY-MM-DD")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="CSV 保存目录")
    parser.add_argument("--adjust", default="hfq", help="复权方式，透传给 cifangquant API")
    parser.add_argument("--force", action="store_true", help="即使 CSV 已存在也重新拉取")
    parser.add_argument("--cash", type=float, default=100000.0, help="初始资金")
    parser.add_argument("--commission", type=float, default=0.001, help="交易佣金比例")
    parser.add_argument(
        "--strategy",
        default="dual_momentum_rotation",
        choices=sorted(STRATEGIES),
        help="回测策略",
    )
    return parser


def print_result(result: BacktestResult) -> None:
    print(f"基金代码: {', '.join(result.symbols)}")
    print(f"初始资金: {result.start_value:.2f}")
    print(f"结束资金: {result.end_value:.2f}")
    print(f"总收益率: {result.total_return:.2%}")
    print(f"最大回撤: {result.max_drawdown:.2f}%")

def main(argv: Optional[Sequence[str]] = None) -> BacktestResult:
    args = build_parser().parse_args(argv)
    csv_paths = fetch_funds_to_csv(
        symbols=args.symbols,
        start_date=args.start,
        end_date=args.end,
        output_dir=args.output_dir,
        adjust=args.adjust,
        force=args.force,
    )
    result = run_backtest(
        csv_paths=csv_paths,
        config=BacktestConfig(
            cash=args.cash,
            commission=args.commission,
            strategy=args.strategy,
        ),
    )
    print_result(result)
    return result


if __name__ == "__main__":
    main()

# python3 main.py --symbols 513030 --start 2024-01-02 --end 2024-12-31 --output-dir data --strategy trend_following
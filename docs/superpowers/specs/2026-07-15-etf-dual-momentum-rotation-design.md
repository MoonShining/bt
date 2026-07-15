# ETF Dual Momentum Rotation Strategy Design

## Goal

Replace the current moving-average crossover backtest strategy with a single ETF dual momentum rotation strategy.

The project should stay lightweight: fetch daily ETF fund bars, write Backtrader-compatible CSV files, run one long-only rotation backtest, and print the existing summary metrics.

## Scope

In scope:

- Remove the public moving-average crossover strategy path from `main.py`.
- Add a Backtrader strategy that rotates among multiple ETF data feeds.
- Use relative momentum to rank ETFs by lookback return.
- Use absolute momentum to stay in cash when no ETF has positive enough momentum.
- Keep existing data download, CSV format, broker setup, commission, and `BacktestResult`.
- Add focused tests for strategy selection behavior and the updated CLI/backtest configuration.

Out of scope:

- Short selling.
- Intraday data.
- Portfolio optimization across many ETFs.
- External benchmark or macro data.
- Rebalancing by real calendar month. The first version will rebalance every fixed number of trading bars.

## Current Context

The repository is a small Backtrader project.

`main.py` currently:

- Parses fund symbols and date ranges.
- Downloads daily fund bars through `CifangQuantClient`.
- Writes `date,open,high,low,close,volume,openinterest` CSV files.
- Runs a `MovingAverageCrossStrategy` over all provided data feeds.
- Returns start value, end value, total return, and max drawdown.

`test_main.py` uses `unittest` and synthetic CSV data. Tests should stay in that style.

## Strategy Rules

### Rebalance Schedule

The strategy evaluates rotation decisions every `rebalance_period` bars.

Defaults:

- `momentum_period`: `60`
- `rebalance_period`: `20`
- `min_momentum`: `0.0`

The first rebalance can only happen after each candidate data feed has enough history for the momentum lookback.

### Relative Momentum

For each ETF, calculate:

```text
momentum = current_close / close_n_bars_ago - 1
```

Rank ETFs by this momentum value from highest to lowest.

### Absolute Momentum

Only ETFs with `momentum > min_momentum` are eligible.

If no ETF is eligible:

- Close any existing position.
- Hold cash until a later rebalance finds an eligible ETF.

### Holding Rule

The strategy holds at most one ETF.

At each rebalance:

- Pick the eligible ETF with the highest momentum.
- Sell all non-selected ETF positions.
- If already holding the selected ETF, keep it.
- If not holding it, use available broker cash to buy as many whole units as possible after commission is considered conservatively by leaving a small cash buffer.

### Orders

The strategy should avoid issuing overlapping orders.

If there is a pending order for any data feed, the current `next()` call skips new rebalance decisions until orders complete, cancel, reject, or hit margin.

## Configuration

`BacktestConfig` should remove moving-average parameters and add rotation parameters:

- `cash`
- `commission`
- `momentum_period`
- `rebalance_period`
- `min_momentum`

The fixed-size `stake` model should be removed for this strategy because rotation should target the selected ETF with nearly all available capital.

## CLI

The CLI should no longer expose moving-average parameters.

Remove:

- `--stake`
- `--fast-period`
- `--slow-period`

Add:

- `--momentum-period`
- `--rebalance-period`
- `--min-momentum`

There is no `--strategy` selector in this first version because the project only keeps one strategy.

Example:

```bash
python3 main.py --symbols 161226,513100,159915 --start 2024-01-01 --end 2024-12-31
```

## Testing

Tests should cover:

- CSV fetch/write behavior remains unchanged.
- `run_backtest()` still loads multiple CSV files and returns a `BacktestResult`.
- With two synthetic ETF CSV files, the strategy can rotate into the ETF with stronger positive lookback momentum.
- When all ETF momentum values are below or equal to `min_momentum`, the strategy keeps or returns to cash.
- CLI parser exposes rotation parameters and no longer exposes moving-average parameters.

The tests should use deterministic synthetic prices. They should not call the real cifangquant API.

## Success Criteria

- The moving-average crossover strategy is removed from the active code path.
- Running a backtest with multiple ETF CSVs uses dual momentum rotation.
- Existing data download and CSV writing still work.
- `python3 -m unittest` passes.
- A smoke backtest using the existing `data/161226_daily.csv` can run successfully, even though a one-symbol candidate pool is not a meaningful rotation universe.

# Macro Trend Following Strategy Design

## Goal

Enhance the existing long-only trend-following strategy in `ai.py` so it combines technical trend signals, macroeconomic risk filtering, staged profit taking, and disciplined stop losses.

The project has no per-stock fundamental dataset. "Fundamental" filtering will therefore be implemented as a macroeconomic proxy using the existing `us10y_daily.csv` 10-year US Treasury yield data.

## Scope

In scope:

- Keep using `MultiPeriodTrendStrategy` as the `trend` strategy behind `main.py`.
- Keep the strategy long-only.
- Use existing daily OHLCV CSV files and existing `us10y_daily.csv`.
- Improve macro risk handling around US 10-year yield level and yield momentum.
- Preserve staged take-profit and ATR/trailing/trend-reversal stop behavior.
- Add focused tests for macro scaling and core exit-state behavior before implementation changes.

Out of scope:

- Short selling.
- Intraday data.
- Real per-stock fundamentals such as revenue, profit, ROE, dividends, or valuation ratios.
- New external data downloads.
- Broad refactors of the backtest runner or batch scripts.

## Current Context

The repository is a lightweight Backtrader project. `main.py` selects `trend` or `mean` strategies and loads daily CSV data through `GenericCSVData`. `ai.py` already defines `MultiPeriodTrendStrategy`, with SMA, RSI, volume confirmation, ATR stop loss, trailing stop, staged take profit, and optional US 10-year yield filtering.

The enhancement should build on that strategy rather than create a second trend strategy. This keeps the public CLI stable and avoids duplicate strategy logic.

## Strategy Rules

### Entry

The strategy may open or add to a long position only when all technical conditions pass:

- Long-term trend filter passes.
- Short, mid, and long SMAs are in bullish order.
- RSI is within the configured pullback range.
- Volume is above the configured volume moving-average threshold.
- The macro filter allows new long exposure.
- Maximum position and add-spacing limits are respected.

### Macro Filter

The US 10-year yield data is used as a macro risk proxy:

- Before 2020, macro filtering remains inactive by default to avoid imposing a modern-rate regime on older data.
- If the current yield is missing, the strategy allows trading and logs a warning when verbose mode is enabled.
- If yield is at or above `us10y_high_threshold`, new entries are blocked.
- If yield is between `us10y_low_threshold` and `us10y_high_threshold`, risk is compressed linearly.
- If yield is below or equal to `us10y_low_threshold`, no yield-level compression is applied.

Add a yield-momentum adjustment:

- Compare the current yield to the yield `us10y_momentum_lookback` trading records earlier.
- If the yield increase is at least `us10y_momentum_threshold`, multiply the risk scale by `us10y_momentum_scale`.
- Yield momentum never increases risk; it only compresses existing risk.
- Missing momentum history leaves the level-based scale unchanged.

### Position Sizing

The existing trend-strength risk model remains the base sizing method:

- Calculate trend strength from SMA spread, RSI position, and volume strength.
- Map trend strength to `base_risk` through `max_risk`.
- Multiply by the macro risk scale.
- Size from risk amount and stop distance.
- Respect total and single-position caps.

### Stops

Stop behavior remains long-only:

- ATR stop is preferred when enabled.
- Fixed percentage stop remains the fallback.
- Trailing stop moves only upward after new highs.
- Consecutive trend reversal bars can exit the position.

The implementation should guard against invalid stop values when ATR is unavailable or non-positive.

### Staged Profit Taking

The staged take-profit model remains:

- First target sells `tp1_ratio` of the current position.
- Second target sells `tp2_ratio` of the current position.
- Third target, or loss of trend after prior targets, closes the remainder.

State flags must reset after a full close.

## CLI

Keep existing CLI behavior:

- `python3 main.py --strategy trend`
- `python3 main.py --strategy trend --us10y-filter`
- Existing `--us10y-high` and `--us10y-low` keep working.

Add optional CLI parameters only if needed for the new momentum adjustment:

- `--us10y-momentum-lookback`
- `--us10y-momentum-threshold`
- `--us10y-momentum-scale`

Defaults should preserve conservative behavior and avoid changing results unless `--us10y-filter` is enabled.

## Testing

Use test-driven development for implementation changes.

Focused tests should cover:

- Yield below low threshold returns scale `1.0`.
- Yield between thresholds returns linear compression.
- Yield above high threshold blocks new entries and returns scale `0.0`.
- Fast yield rise applies the additional momentum compression.
- Missing yield data allows trading and returns scale `1.0`.
- Full position close resets take-profit flags and stop state.

Backtrader integration can be kept small by constructing strategy instances through a minimal Cerebro run with synthetic daily data where needed.

## Success Criteria

- `trend` remains the default strategy path in `main.py`.
- Existing CSV data can run without external downloads.
- The strategy is still long-only.
- Macro filtering works from `us10y_daily.csv`.
- Tests demonstrate the new macro scaling behavior before code changes are accepted.
- A smoke backtest command runs successfully after implementation.

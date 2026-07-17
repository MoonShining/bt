# Trend Following ATR Exits Design

## Goal

Enhance `TrendFollowingStrategy` with disciplined exit behavior:

- Use an ATR-based stop line as a hard exit.
- Keep profits running while the trend remains intact.
- When the trend reverses, exit in two stages instead of selling everything immediately.

## Scope

This change only affects `strategy/trend_following.py` and focused strategy tests.

It preserves the current moving-average selection model and the current default periods of `fast_period=14` and `slow_period=30`.

## Entry Behavior

The strategy remains long-only. It selects the strongest data feed whose close is above the slow average and whose fast average is above the slow average.

When a selected feed has no position, the strategy invests available cash multiplied by `cash_buffer`.

## ATR Stop

Each data feed gets an ATR indicator.

After a buy fills, the strategy records an entry price and starts a stop line at:

```text
entry_price - atr_multiplier * ATR
```

While the position is open, the stop line trails upward when the close makes new highs:

```text
highest_close - atr_multiplier * ATR
```

The stop line never moves downward. If the close is at or below the stop line, the strategy closes the full position immediately.

If ATR is missing or non-positive, the strategy does not create or update a stop line for that bar.

## Trend Reversal Exits

A trend reversal means either:

- close is below the slow average, or
- fast average is at or below the slow average.

When a position sees its first reversal bar, the strategy sells 50% of the current position.

If the next bar still shows reversal, the strategy closes the remaining position.

If the trend recovers before the second reversal exit, the staged exit state resets and the strategy continues holding the remaining position.

## Order Handling

The strategy keeps at most one outstanding order per data feed.

Full closes reset entry, stop, high-water mark, and reversal-exit state.

## Tests

Focused Backtrader tests should use synthetic daily OHLCV data and cover:

- ATR stop exits the full position.
- Trend reversal exits half first, then the remainder on the next reversal bar.
- Trend recovery after the first reversal resets the staged-exit state.

# Signal Vault Crypto V6 — Gated Strategy-Family Tournament

V6 is an offline research process. It is not an execution strategy and does not
authorize live trading.

## Why V5 is rejected

V5 tested a bidirectional long/short/cash regime model and failed both the
development and unseen cross-venue holdout periods.

- 2026 H1 development: -11.96%, profit factor 0.6556, negative expectancy,
  12.08% maximum closed-balance drawdown.
- 2025 Q4 Binance cross-venue holdout: -15.01%, profit factor 0.3983,
  negative expectancy, 15.36% maximum closed-balance drawdown.
- Both long and short sides were negative.
- The dominant failure remained excessive hard-stop frequency relative to the
  fixed friction model.

The next experiment therefore changes the research process rather than merely
moving one strategy's thresholds.

## V6 design frozen before the next holdout

V6 evaluates a small predeclared tournament on 2026 H1 Kraken development data.

Candidate dimensions:
- timeframe: 1h or 4h
- family:
  - trend momentum
  - breakout
  - trend pullback
- regime strictness: base or strict
- target/stop:
  - +5.0% / -2.0% gross
  - +7.0% / -2.5% gross

This creates 24 fixed candidates.

All candidates:
- can be long, short, or cash
- require BTC and pair direction to agree
- use completed candles only
- enter at the next candle open
- are exposed to the entry candle's high/low
- assume stop first if stop and target are both touched in one bar
- deduct a fixed 0.74% round-trip friction from every completed trade
- use no leverage benefit and no funding-rate benefit
- use at most four simultaneous positions with $15 nominal stake on a $100
  logical research wallet

## Development gate

A candidate is eligible for holdout testing only if, on 2026 H1 development:

1. Total net return is positive.
2. Profit factor is greater than 1.10.
3. Expectancy per trade is positive.
4. Maximum closed-balance drawdown is below 10%.
5. It completes at least 30 trades.
6. At least four of January through June are positive.

If no candidate passes all six conditions, the next holdout is not downloaded or
examined.

If multiple candidates pass, selection is deterministic and favors:
1. more positive months
2. higher total return
3. higher profit factor
4. higher median monthly P&L
5. lower drawdown

## Holdout discipline

2025 Q3 Binance spot is declared as the next unseen cross-venue holdout before
the V6 tournament is run.

Only the single development-selected candidate may consume the holdout.

The selected candidate passes the holdout only if:
- net return is positive
- profit factor is greater than 1.20
- expectancy is positive
- maximum closed-balance drawdown is below 8%
- at least 15 completed trades occur
- at least two of the three Q3 months are positive

Passing V6 only permits a futures-native Freqtrade PAPER implementation with
venue-specific fees, funding, lookahead analysis, recursive analysis, and
forward observation. It does not authorize real-money trading.

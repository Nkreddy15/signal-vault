# Signal Vault Crypto V4 — Predeclared Research Gate

V4 is a research/PAPER candidate created after V3 failed its frozen Q2 gate.
It is not authorized for live trading.

## Why V3 is rejected

V3 improved drawdown and reduced churn versus V2, but it still failed:
- full Q2 net return was negative
- profit factor remained below 1.0
- expectancy remained negative
- April, May, and June were all negative
- June produced 10 trades and every one stopped out

The June result shows that pair-local trend logic can still admit temporary
bullish setups inside a broader crypto drawdown.

## V4 design frozen before results

- timeframe: 1h
- long-only Kraken spot research/PAPER
- BTC/USD is used as an informative market-regime guard
- no trade unless BTC itself is in a positive 7-day / long-term trend regime
- pair must remain above a rising EMA200 with EMA20 > EMA50 > EMA200
- pair must have positive 3-day and 7-day structure
- exactly one entry family:
  - pullback to the trend followed by price re-acceleration above the recent
    3-hour high
- minimum movement-capacity gate: 2.5%
- minimum adaptive gross target: 3.5%
- maximum adaptive target: 6.0%
- hard stop: -1.2% gross before modeled exchange fees
- BTC risk-off and pair-regime failure exits can close a deteriorating trade
  before the hard stop
- no shorts, leverage, or live credentials

## Data discipline

Q2 2026 informed the design of V4 and is therefore treated as development
evidence, not a clean holdout.

Q1 2026 is declared as the unseen holdout before V4 is run. Kraken's official
quarterly OHLCVT archive is used for both quarters. Exact pair matching is
required and all six pairs must have complete hourly coverage.

## V4 gate

V4 is rejected unless all of the following hold:

1. Q1 2026 holdout net P&L is positive after modeled exchange fees.
2. Q1 holdout profit factor is above 1.10.
3. Q1 holdout expectancy per trade is positive.
4. Q1 holdout maximum closed-trade drawdown is below 8%.
5. Q1 holdout contains at least 15 completed trades.
6. Q2 development-period result is not materially negative.
7. At least four of the six monthly folds from January through June are
   positive.
8. Results are not dependent on one pair producing nearly all gains.
9. No dataset-integrity warning indicates wrong-pair matching or severe
   synthetic-fill behavior.

Passing this gate only permits further PAPER testing. It does not authorize
real-money trading.

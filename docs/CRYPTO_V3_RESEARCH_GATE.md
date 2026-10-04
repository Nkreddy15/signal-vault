# Signal Vault Crypto V3 — Predeclared Research Gate

V3 is a research/PAPER candidate created only after V2 failed its frozen
screening gate. It is not authorized for live trading.

## Why V2 is rejected

The first Q2 2026 V2 backtest produced 154 trades, -16.83% total return,
profit factor 0.49, negative expectancy, and 17.50% closed-trade drawdown.
Every V2 entry tag was negative on aggregate. The main failure mode was not
small winners: volatility-target exits averaged +2.81%. The failure was entry
quality and the number of losing trades, including 62 stop-loss exits.

One data-quality defect was also found: the Kraken archive loader matched
MSOLUSD instead of SOLUSD because of substring matching. That does not explain
the broad V2 failure because BTC, ETH, XRP, ADA, and DOGE were also negative,
but V3 fixes the loader before any further comparison.

## V3 design frozen before results

- timeframe: 1h
- long-only Kraken spot research/PAPER
- corrected exact six-pair archive matching
- strict bullish regime:
  - close above EMA200
  - EMA20 > EMA50 > EMA200
  - positive EMA50 and EMA200 slopes
  - positive 72-hour return
- only two entry families:
  - 24-hour momentum
  - trend pullback/reclaim
- no breakout-only entry
- no generic continuation entry
- cost-aware movement-capacity gate
- minimum adaptive gross profit target: 3.0%
- maximum adaptive target: 6.0%
- hard stop: -1.5%
- normal regime-failure exit requires persistent structure failure and at least
  -0.9% gross trade loss
- 72-hour stale-trade handling
- no shorts, leverage, or live credentials

## Screening protocol

The research runner performs:
1. Full Q2 2026 backtest.
2. April fold.
3. May fold.
4. June fold.

V3 is worth further PAPER research only if:

1. Full-quarter net P&L is positive after Freqtrade's modeled exchange fees.
2. Profit factor is above 1.10.
3. Expectancy per trade is positive.
4. Closed-trade maximum drawdown is below 10%.
5. There are at least 20 completed trades in the full-quarter test.
6. At least two of the three monthly folds are positive.
7. Aggregate results are not dependent on a single pair.
8. No dataset integrity warning indicates the wrong asset or severe synthetic
   fill behavior.

Passing these gates only permits additional PAPER testing. It does not authorize
real-money trading.

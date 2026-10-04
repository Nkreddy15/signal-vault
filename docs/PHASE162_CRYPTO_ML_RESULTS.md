# Phase 162 — Crypto ML tournament results

Date: 2026-10-02

This report records actual OFFLINE historical results from the preserved
GitHub Actions artifact `crypto-90day-candidate-research-36927348918`.

Dataset:
- 6 crypto assets: AVAX/USD, BTC/USD, ETH/USD, LINK/USD, LTC/USD, SOL/USD
- 2160 aligned hourly bars per asset
- 2026-06-27 18:00 UTC through 2026-09-25 18:00 UTC
- no broker orders
- no PAPER/LIVE promotion

Models:
- logistic regression
- random forest
- histogram gradient boosting

Causal features:
- returns over 1h, 3h, 6h, 12h, 24h, 48h, 168h
- EMA 12/26 spread
- EMA 24/72 spread
- 24h and 72h realized volatility
- candle range
- 24h volume z-score
- cross-sectional 24h relative-strength rank

The split was chronological with no shuffling. Confidence thresholds were
selected using validation only; test data remained untouched until final
evaluation.

## 1-hour target

All three models failed after estimated costs in the untouched test window.

| Model | Threshold | Test trades | Long | Short | Gross return sum | Base-cost net return sum | Win rate | Expectancy/trade | Max DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Logistic L2 | 0.60 | 164 | 92 | 72 | +2.79% | -118.57% | 21.95% | -0.723% | 69.96% |
| Random forest | 0.60 | 251 | 229 | 22 | +20.16% | -165.58% | 14.34% | -0.660% | 81.36% |
| Hist gradient boosting | 0.70 | 237 | 163 | 74 | +7.77% | -167.61% | 15.19% | -0.707% | 81.83% |

Interpretation: several models produced positive gross directional return sums,
but one-hour turnover plus the deliberately conservative base friction estimate
destroyed the result. These models are NOT candidates for PAPER promotion.

## Longer-horizon follow-up

To test whether the failure was caused mainly by excessive turnover, the same
causal feature family was re-evaluated using non-overlapping 4h, 12h and 24h
research horizons.

### 4-hour target

All models remained negative after base costs.

- Logistic: 55 test trades, base net sum -37.29%
- Random forest: 74 test trades, base net sum -36.30%
- Hist gradient boosting: 200 test trades, base net sum -111.77%

### 12-hour target

All models remained negative after base costs.

- Logistic: 20 test trades, base net sum -28.27%
- Random forest: 23 test trades, base net sum -12.56%
- Hist gradient boosting: 103 test trades, base net sum -51.62%

### 24-hour target

Random forest was the only model with a positive result under the LOW friction
scenario, but it still failed the BASE scenario:

- Random forest: 23 test trades
- gross return sum: +11.89%
- low-friction net return sum: +1.77%
- low-friction compounded return: +1.23%
- base-friction net return sum: -5.13%
- base-friction compounded return: -5.53%
- base-friction expectancy/trade: -0.223%
- base-friction max drawdown: 17.06%

This is not sufficient evidence for promotion. It is a useful lead: lower
turnover and longer holding horizons materially improved economics, so the next
research iteration should focus on higher-quality / lower-turnover entries,
cross-sectional ranking, regime filters, and explicit fee-aware thresholds
rather than forcing more trades.

## Decision

- 1h ML tournament: FAIL
- 4h ML tournament: FAIL
- 12h ML tournament: FAIL
- 24h random forest: INTERESTING UNDER LOW FRICTION, FAILS BASE COST SCREEN
- automatic PAPER promotion: DISABLED
- real-money trading: NOT AUTHORIZED

The failure is retained as evidence. We will not hide it behind a dashboard or
paper activity.

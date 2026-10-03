# Signal Vault Crypto V5 — Bidirectional Research Gate

V5 is an offline research candidate, not an execution strategy and not trading
authorization.

## Why V4 is rejected

V4 reduced drawdown but failed the return gate:
- Q1 2026 holdout: -1.99%, profit factor 0.46, negative expectancy.
- Q2 2026 development: -3.26%, profit factor 0.21.
- All six monthly folds from January through June were negative.
- The dominant failure remained long entries hitting hard stops in broadly
  falling crypto markets.

The January-June development window itself was strongly negative, so another
long-only spot variation is not the next experiment.

## V5 hypothesis frozen before the new holdout

V5 tests a long / short / cash regime model on 1h candles.

- Long only when BTC and the candidate pair are both in strong bullish regimes.
- Short only when BTC and the candidate pair are both in strong bearish regimes.
- Otherwise remain in cash.
- Entries require a pullback/retrace followed by re-acceleration in the regime
  direction.
- Signals are evaluated on completed candles and entries occur at the next
  candle open.
- Gross target: 3.5%.
- Gross hard stop: 1.2%.
- Fixed round-trip friction deduction: 0.74% on every completed trade.
- If target and stop are both touched in one hourly candle, the simulator
  assumes the stop happened first.
- 1x directional return only; no leverage benefit.
- Funding costs are not modeled, so a pass is only permission to perform a
  futures-native PAPER/backtest next.

## Data discipline

2026 H1 (Q1 + Q2) is development evidence because it has already been inspected.

2025 Q4 is declared as the next unseen holdout before V5 is run.

## V5 gate

V5 is rejected unless all of these hold:

1. 2025 Q4 holdout return is positive after the 0.74% friction deduction.
2. Holdout profit factor is above 1.20.
3. Holdout expectancy per trade is positive.
4. Holdout closed-balance drawdown is below 8%.
5. Holdout has at least 20 completed trades.
6. 2026 H1 development result is positive.
7. Both long and short sides are individually reported; neither side may hide a
   large loss behind the other.
8. Results are not dependent on one pair for nearly all gains.
9. At least two of the three Q4 monthly buckets are positive.

Passing this gate does not authorize live trading. The next step after a pass is
a futures-native Freqtrade PAPER implementation with funding, exchange-specific
fees, lookahead analysis, and recursive analysis.

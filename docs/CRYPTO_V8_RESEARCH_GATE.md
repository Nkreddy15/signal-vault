# Signal Vault Crypto V8 — Short-Only Bear-Breakout Gate

V8 is an offline research process. It does not submit exchange/broker orders and
does not authorize live trading.

## Why V7 is rejected

V7 found one nearly breakeven development candidate after the fixed 0.74%
round-trip friction assumption:

- 41 trades
- +0.11% net return
- profit factor 1.0082
- 3 positive months out of 6
- 8.14% maximum closed-balance drawdown

That candidate still failed the frozen gate.

The important decomposition was directional:
- long side: 15 trades, -$5.31, 0% winners
- short side: 26 trades, +$5.43, positive gross and net expectancy

The next hypothesis is therefore frozen as short-only before the Q3 holdout is
consumed.

## V8 candidate family

V8 trades only short breakouts during aligned BTC + pair bear regimes.

Candidate dimensions:
- breakout lookback: 72h, 96h, 144h
- target / stop:
  - +10% / -3.5% gross
  - +12% / -4.0% gross
- cooldown after pair exit: 24h or 48h

This creates 12 fixed candidates.

All candidates:
- use completed 1h candles only
- enter at the next candle open
- are immediately exposed to the entry candle high/low
- assume stop first if target and stop occur in the same candle
- deduct 0.74% round-trip friction from every completed trade
- use no leverage benefit and no funding-rate benefit
- use at most three simultaneous positions
- cap holding time at 10 days

## Development gate

A V8 candidate may consume the 2025 Q3 holdout only if, on 2026 H1 Kraken
development data:

1. Net return is above +2.0%.
2. Profit factor is above 1.20.
3. Expectancy is positive.
4. Maximum closed-balance drawdown is below 8%.
5. At least 18 completed trades occur.
6. At least four of January through June are positive.

If no candidate passes, Q3 remains unseen.

## Holdout gate

2025 Q3 Binance spot remains the predeclared unseen cross-venue holdout because
V6 and V7 did not consume it.

Only the single development-selected V8 candidate may consume it.

The candidate passes only if:
- holdout net return is positive
- profit factor is above 1.20
- expectancy is positive
- maximum drawdown is below 8%
- at least eight completed trades occur
- at least two of July, August, and September are positive

Passing V8 permits only a futures-native PAPER implementation with
venue-specific fees, funding, lookahead analysis, recursive analysis, and
forward observation. It does not authorize real-money trading.

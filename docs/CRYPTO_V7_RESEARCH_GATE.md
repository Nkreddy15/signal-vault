# Signal Vault Crypto V7 — Low-Turnover Breakout Gate

V7 is an offline research process. It does not submit orders and does not
authorize live trading.

## Why V6 is rejected

All 24 V6 candidates failed the frozen 2026 H1 development gate. The least-bad
candidate was the strict 1h breakout family, but it was still negative after
the 0.74% round-trip friction model.

The next hypothesis is therefore specific: the strict 1h breakout family may
have a small gross directional edge that is being overwhelmed by turnover.

## V7 design frozen before the next holdout

V7 only studies low-turnover 1h breakouts.

Candidate dimensions:
- breakout lookback: 48h or 96h
- gross target / stop:
  - +8% / -3%
  - +12% / -4%
- per-pair cooldown after exit: 24h or 48h
- absolute-strength or relative-strength confirmation versus BTC

This creates 16 fixed candidates.

All candidates:
- can be long, short, or cash
- require BTC and pair regime agreement
- require a high-volume breakout
- require at least 0.8% hourly ATR
- enter at the next candle open after a completed signal candle
- are exposed to the entry candle high/low immediately
- assume stop first if target and stop are both touched in one candle
- deduct 0.74% round-trip friction from every completed trade
- use no leverage benefit and no funding-rate benefit
- use at most three simultaneous positions
- cap holding time at 10 days
- report gross expectancy and the break-even friction level

## Development gate

A candidate is eligible for the unseen holdout only if, on 2026 H1 Kraken data:

1. Net return is positive after 0.74% friction.
2. Profit factor is above 1.15.
3. Expectancy is positive.
4. Maximum closed-balance drawdown is below 8%.
5. At least 15 completed trades occur.
6. At least four of January through June are positive.

If no candidate passes, the 2025 Q3 holdout remains unseen.

## Holdout gate

2025 Q3 Binance spot remains the predeclared unseen cross-venue holdout because
V6 did not consume it.

Only one development-selected candidate may consume it.

The candidate passes only if:
- net return is positive
- profit factor is above 1.20
- expectancy is positive
- maximum drawdown is below 8%
- at least eight completed trades occur
- at least two of July, August, and September are positive

Passing V7 permits only futures-native PAPER implementation and further
validation. It does not authorize real-money trading.

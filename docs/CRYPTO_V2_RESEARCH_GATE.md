# Signal Vault Crypto V2 — Predeclared Research Gate

V2 is a research/PAPER candidate. It is not a live-money strategy and passing
this gate does not establish future profitability.

## Why V2 exists

V1 was intentionally a high-activity execution harness. Its fixed +0.40% ROI
reference was smaller than the existing Signal Vault base round-trip friction
assumption (~0.74%), so it was useful for plumbing tests but structurally weak
as a profit-seeking candidate.

V2 changes the objective from "generate enough trades to test the stack" to
"only enter when the recent market structure has enough movement capacity to
justify the friction budget."

## Frozen V2 design before results

- timeframe: 15m
- startup warmup: 210 candles; restart never forces an entry, but V2 does not
  require every soft regime test to remain true at once after restart
- long-only Kraken spot PAPER/dry-run
- six-pair universe from the existing config
- bullish regime required, but evaluated with a scored regime instead of
  requiring every soft trend condition simultaneously; price must remain
  above EMA200 and EMA20 must remain above EMA50
- setup confirmation: momentum, breakout, pullback continuation,
  trend continuation, or multiple confirmations
- assumed round-trip friction used by the entry gate: 0.74%
- minimum movement-capacity gate: 1.80%
- minimum adaptive gross profit target: 2.20%
- hard stop: -1.80%
- profit protection is not allowed before gross profit reaches at least 1.60%
- no mean-reversion-only entries
- V2 uses its own PAPER database and must not inherit V1 trades

The movement-capacity filter is a volatility/range screen, not a prediction of
future return.

## First screening data

Default local screening downloads 90 days of public Kraken history and converts
it to 15m candles. This is historical evidence only.

## V2 screening gate

Do not tune V2 after looking at one attractive number. The first frozen version
is considered worth further work only if all of the following are true:

1. Net P&L after the backtest's exchange fees is positive.
2. At least 30 closed trades are present, so the result is not based on a tiny
   handful of lucky trades.
3. Profit factor is above 1.10.
4. Expectancy per closed trade is positive.
5. Maximum account drawdown is below 10%.
6. Results are not dependent on one coin producing nearly all gains.
7. When the same frozen rules are checked on chronological sub-periods, at
   least two of three periods are positive and aggregate P&L remains positive.

Failing the gate means V2 remains a rejected/research version. We then diagnose
the failure and design V3 from the evidence instead of silently curve-fitting
V2.

## Promotion boundary

Passing this gate only permits a V2 PAPER trial. It does not permit live
trading, real-money activation, leverage, shorting, or automatic strategy
promotion.

## Restart-resilience revision

Before the first meaningful multi-asset backtest, V2 was revised so inactivity
cannot be caused solely by one soft regime condition staying false after a
restart. The cost gate, minimum gross target, hard stop, PAPER-only boundary,
and separate V2 database were not loosened. A restart still never creates a
trade by itself; the strategy must see a valid cost-aware setup.

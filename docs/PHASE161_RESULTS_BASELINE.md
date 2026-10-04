# Phase 161 — Verified results baseline before further strategy work

Date: 2026-10-02

This document is the evidence baseline for the Signal Vault reset. It exists to
prevent infrastructure progress, dashboards, container health, or trade activity
from being confused with strategy quality.

## Verified crypto result already available

GitHub Actions run 36943614707 replayed the predeclared 90-day crypto
strength-tilt research against 2160 historical hours.

Result:
- `full-invested-top2-moderate-168h-weekly-v1-predeclared`: failed support in
  low, base, and high illustrative friction scenarios.
- `full-invested-top2-strong-168h-weekly-v1-predeclared`: failed support in
  low, base, and high illustrative friction scenarios.
- No strategy selected.
- PAPER activation was not permitted by that research receipt.
- This negative result is retained; it must not be hidden by later experiments.

## Verified US-equity result already available

Source: preserved Library audit
`2026-09-29_six-stock_independent_XNYS_and_clock_audit.json`, tied to
GitHub Actions run 36637836735.

Universe:
- AAPL
- AMD
- MSFT
- NVDA
- QQQ
- SPY

Coverage:
- 10 XNYS sessions
- 60 complete regular-core hourly bars per asset
- 360 aggregate asset-hour records
- one shared hypothetical $100 bankroll
- $30 exposure cap

Exit-inclusive historical P&L:

| Candidate | Low friction | Base friction | High friction | Synthetic fills |
| --- | ---: | ---: | ---: | ---: |
| Cash | $0.00 | $0.00 | $0.00 | 0 |
| EMA 12x26 | -$0.15 | -$0.19 | -$0.30 | 5 |
| Momentum 24-bar / 50 bps | +$2.56 | +$2.54 | +$2.46 | 2 |
| Passive comparator | +$2.56 | +$2.54 | +$2.46 | 2 |

Important: the momentum candidate and passive comparator produced identical
hypothetical fills in this short sample. Therefore this does NOT establish a
momentum edge. The preserved audit explicitly labels the sample
`TOO_SHORT_TO_VALIDATE_ALPHA`.

## Reset acceptance rule

Do not spend more time on dashboard polish or declare progress from container
health alone.

The next strategy work must produce a comparable results table containing at
least:
- market and universe,
- historical period,
- train/development and out-of-sample/walk-forward split,
- trade count,
- after-cost P&L,
- benchmark P&L,
- win rate,
- expectancy,
- maximum drawdown,
- turnover/fees,
- strategy/model family,
- clear PASS/FAIL reason.

Existing open-source engines/strategies should be reused where practical instead
of rebuilding commodity trading infrastructure.

PAPER execution is for verifying order/execution behavior after a candidate has
historical evidence; PAPER activity by itself is not evidence of profitability.

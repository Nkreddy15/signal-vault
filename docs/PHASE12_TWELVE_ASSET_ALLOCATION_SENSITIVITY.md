# Phase 12 — Does the arbitrary two-position priority drive our 12-market history?

The first successful synchronized source-and-model run was
[GitHub Actions #36647061726](https://github.com/Nkreddy15/signal-vault/actions/runs/36647061726).
Both stages passed and the credential-free second job produced report SHA:
`d7ad87d5c3e5a21ddddec111be311e0bc2c67006474b306f6e1eb8698e65339f`.
The owner-approved September six-crypto original archive and original
six-stock September IEX artifact were BOTH privately preserved in
`/Signal Vault/Research/` before GitHub's seven-day retention expires.

The fully source-SHA-audited historical comparison had 60 common XNYS
regular-core hourly stamps, 32 XNYS stamps AFTER the common 28-bar
indicator warmup, and an aligned research horizon
**2026-09-18 18:00Z – 2026-09-25 20:00Z**. The one shared
hypothetical $100 account retains its $15 entry and $30 total-long
exposure caps, while crypto can generate independent correctly dated
events during XNYS overnight/closed sessions.

## Observed limitation: global alphabetical same-clock ordering

The original simulator processes synthetic SELLs before BUYs and orders
otherwise simultaneous candidates globally by alphabetical symbol.
When all twelve fixed passive candidates simultaneously signal BUY,
only the first **two** $15 requests can be admitted. This means
`AAPL` + `AMD` enter first (stock alphabetically before crypto);
momentum happened to admit the SAME two synthetic stock buys during
this PARTICULAR short backtest. Their identical modeled after-cost
P&L is NOT two independent validations, and the result cannot be
called a diversified 12-asset portfolio.

### Preregistered sensitivity, with NO hindsight-based winner selection

Phase 12 adds only an OPTIONAL explicitly aligned
`allocation_priority_order` argument to the research-only shared
portfolio simulator. It must contain each and every already registered
instrument exactly once and cannot be passed to older unscoped
simulation paths. The old default symbol-alphabetical behavior, all
previously stored historical source hashes and old report JSON stay
unchanged byte-for-byte.

`cross_market_joint_review.py` can now report THREE additional
purely descriptive fixed tie policies under the SAME four original
hypotheses, three ORIGINAL illustrative class-level friction scenarios,
same fixed common indicator/historical cutoff, same total $100 and
$30 exposure limits, and one invariant source cohort:

- **Stock-first alphabetic:** AAPL, AMD, MSFT, NVDA, QQQ, SPY, then
  AVAX, BTC, ETH, LINK, LTC, SOL.
- **Crypto-first alphabetic:** AVAX, BTC, ETH, LINK, LTC, SOL, then
  AAPL, AMD, MSFT, NVDA, QQQ, SPY.
- **Alternating stock/crypto alphabetic:** AAPL, AVAX, AMD, BTC,
  MSFT, ETH, NVDA, LINK, QQQ, LTC, SPY, SOL.

These are counterfactual allocation conventions, NOT algorithmic
portfolio optimization, predictive signals, recommended coins/stocks,
independent experiments or proposals to give every asset an individual
$100. The report retains the **unaltered original alphabetical
baseline** beside the separately named sensitivity cases, and
explicitly reports admitted hypothetical BUY-symbol order,
exit-cost-inclusive P&L, estimated fees, sampled drawdown and rejected
entries. No outcome is used to select a priority policy or strategy.

## Completely unattended historical replay on merge

A standalone reviewed workflow,
`.github/workflows/offline-12-market-allocation-sensitivity.yml`,
automatically starts on the PRIVATE GitHub repo's main-branch merge
of this precise Phase 12 research code/workflow ONLY. It is not a
new DATA GET/cron or API connection and does not access Railway.

This job uses **GitHub Actions read-only token only**, downloads the
exact immutable prior manual source artifacts from runs
`36647061726` (September six-crypto) and `36637836735`
(six-stock IEX), independently checks BOTH source manifests
and exact original stock report SHA, independently reconstructs the
full calendar and both historical model reports, then calculates
the explicitly requested optional sensitivity scenarios. It uploads
a private `offline_twelve_market_allocation_sensitivity.json` for
7 days. A missing/expired source artifact or SHA mismatch FAILS CLOSED:
no silent re-download from Alpaca and no invented comparison.

No GitHub Actions repo secrets are passed, no historical provider
request/paid SIP/account query/PAPER or LIVE broker order is generated.
Successful historical diagnostics do not establish future trading edge,
investment advice, fractional-stock executability or authority to
auto-trade.

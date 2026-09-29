# Phase 6 — corrected research risk semantics and reproducible v1 → v2 replay

**All changes here are historical/offline research only.** The installed
Railway `btcusd-hourly-get-cron`, its persistently mounted original forward
journal, private market-data variables, separately authorized one-time
$15 BTC PAPER diagnostic BUY, and all original GitHub v1 research archives
stay untouched. No automatic PAPER/LIVE order worker or market-data refresh
is enabled by this PR.

## Audit finding and correction

The original September 29 Phase 5 multi-asset simulation carried a boolean
`buys_blocked=True` forward for the **entire historical sample** whenever
either the $3 UTC daily-loss cap OR $10 peak-drawdown cap was exceeded.
That treated a daily loss limit like a permanent portfolio halt; a subtle
error that can inflate rejections and change multi-day estimated P&L.
The first real BTC/ETH historical report is therefore retained as a distinct
**preliminary v1 record**, not overwritten or quietly compared as if it were
v2.

Both synthetic single-asset and shared one-$100 portfolio simulators now
explicitly apply:
- $3 **UTC daily loss**: block new hypothetical BUY entries through that
  UTC date, reset the daily gate at the next UTC date. The new date's
  baseline uses only already completed prior marks (never the new bar close).
- $10 **peak drawdown**: once breached, durably block new hypothetical BUYs
  for the remainder of this backtest, even on a new date; do not confuse
  it with a daily reset.
- SELL signals remain synthetic research and may be processed despite
  blocked new BUYs. There is **no** broker liquidation, execution or new
  permission granted by either condition.
- Both branches record the version
  `v2_utc_daily_reset_plus_persistent_peak_drawdown_halt`, pause dates
  and persistent-peak status. Rejection details distinguish daily pause
  from persistent peak halt.
- Shared-book `previous_closed` now bisects the quality-validated
  per-symbol close index instead of scanning the whole historical series
  for every cross-asset event. This removes that avoidable quadratic lookup
  cost before six-symbol and twelve-symbol research expansion.

## Replay the SAME originally downloaded data, without data keys

The existing successful user-triggered private historical DATA GET is
**GitHub run 36632386959** (2026-09-29). It recorded 1,488 historical
hourly closes each for BTC/USD and ETH/USD during July 1–September 1,
five SHA-addressed 14-day-or-shorter files, and a v1 after-cost research
report with SHA
`322c38bf00eaa00ad65d96aafe0ad63c871ac9faba867accad2b5d03b9a01802`.
Those rows are **retrospective**, not genuinely prospective. The source
GitHub Actions artifact expires after 7 days; if replay is attempted
later, restore that original artifact through a separately validated
private source rather than silently asking Alpaca for a different
historical dataset.

This PR introduces a new **manual** workflow:

`.github/workflows/manual-replay-crypto-research-v2.yml`

[Open the offline replay workflow](https://github.com/Nkreddy15/signal-vault/actions/workflows/manual-replay-crypto-research-v2.yml)

Choose main, retain default source run ID `36632386959`, and click
**Run workflow**. This workflow uses only an Actions-scoped `GITHUB_TOKEN`
to fetch the ORIGINAL private historical artifact; it does not read
`SIGNAL_VAULT_RESEARCH_DATA_KEY_ID`,
`SIGNAL_VAULT_RESEARCH_DATA_SECRET`, Railway secrets, Keychain or any
Alpaca network API. It independently verifies:

1. Source filename, SHA, symbol group, provider feed, requested window
   chronology and historical-only classification, before writing results.
2. A fresh owner-private 0700 research folder and exact 0600 copies of the
   five original SHA-bound archives; the original source ZIP stays unchanged.
3. All three identical predeclared *illustrative* low/base/high friction
   assumptions, with all four fixed hypotheses and ONE shared $100
   hypothetical portfolio.
4. A new versioned `offline_research_analysis.json` SHA and
   `replay_manifest.json` mapping every source archive hash and the
   old/new analysis-report hashes. If any source file/window is missing,
   malformed or tampered, fail closed with no invented results.

Only the corrected v2 report and provenance manifest are re-uploaded
privately with 7-day retention. No historical provider call, additional
API secrets, asset order, reclassification or strategy promotion is
performed. A historical result never proves a predictive edge.

## What remains after this correction

The fixed historical rule is a **research risk policy**, not a trading
engine. It doesn't imply any crypto/stock market data beyond the symbols
actually captured, and it doesn't automatically select a hypothesis based
on the untouched holdout. Expand a bounded, verifiably entitled multi-asset
dataset and independently calibrated current per-asset costs before making
a trading-permission or budget decision. Keep BTC prospective collection
under a separate provenance source (Railway's successful 21:11 UTC first
cloud observation on September 29 already exists).

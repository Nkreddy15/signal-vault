# Phase 5: manual historical DATA GET + automatic OFFLINE analysis

This phase adds **no new autonomous trigger**. The owner starts the GitHub
Actions `Manual multi-crypto historical DATA GET (research only)` workflow
on the PRIVATE `Nkreddy15/signal-vault` default branch when ready.

## Why one manual click now produces a complete research deliverable

1. A zero-secret historical plan validates 1–6 predeclared crypto symbols,
   UTC start/end, and at most 30 chunks of 14 days each.
2. In exactly ONE explicitly approved step, fixed-allowlist authenticated
   Alpaca historical **DATA GET** reads two independent encrypted
   repository Actions secrets. They never enter git, outputs, command-line
   arguments or the analysis step.
3. The new `ci_historical_report.py` independently rereads SHA-named
   private historical archives, verifies **every requested window**,
   symbols, provider/feed, content hash, full closed-bar chronology and
   historical-only label; missing or unexpected archives FAIL CLOSED.
4. Three PREDECLARED cost stress scenarios are run completely OFFLINE:
   illustrative low (15bps fee/2bps full spread/5bps slippage per side),
   base (25/4/10bps) and high (40/12/20bps). These are ESTIMATES,
   **not** claims of actual current brokerage commission or market spreads.
   All compared instruments receive the same assumptions within each
   illustrative scenario for preliminary broad-screen analysis. Actual
   per-symbol fee/quote calibration must be done before promotion.
5. Each report includes four fixed descriptive cash/passive/EMA/momentum
   hypotheses on development, validation and an untouched chronological
   test fold, plus **four different simulations of the same ONE $100
   shared multi-asset portfolio**, not one $100 per instrument. Report
   includes modeled exit-inclusive P&L, turnover, estimated fees,
   maximum sampled mark drawdown, and an explicit no-edge-proof label.
   NO test-set winner is selected automatically.
6. The full historical archives, cost-assumption files and one
   SHA-identifiable `offline_research_analysis.json` report are uploaded
   as a PRIVATE Actions artifact for **7 days**. No historical asset
   bar can be counted as a genuinely prospective forward observation.

The analysis step is separate from the ONE credentialed GET step and has no
secret variables, network requests or broker account integration. On a
validation failure, the workflow reports `BLOCKED`; it does not fabricate
missing data, overwrite a research archive, silently relabel historical
candles, or submit any PAPER/LIVE order.

## How to launch when ready

Secrets must be placed **in the GitHub repository Actions settings**, NOT
Railway variables or this chat:

- `SIGNAL_VAULT_RESEARCH_DATA_KEY_ID`
- `SIGNAL_VAULT_RESEARCH_DATA_SECRET`

Navigate to [the manually started workflow](https://github.com/Nkreddy15/signal-vault/actions/workflows/manual-historical-crypto-research.yml).
Choose `main` and the initial default **BTC/USD ETH/USD**, with historical
UTC 2026-07-01T00:00:00Z to 2026-09-01T00:00:00Z. Click
**Run workflow** once; setting the secrets alone does not start it.
GitHub will produce a new `workflow_dispatch` run; do not confuse it
with the automatically run `Signal Vault paper-only safety checks` suite.
This GET-only historical backfill is not an automatic hourly collector.

The first real data/research report should be reviewed for entitlement,
per-asset missing hours, timestamp conventions and estimated costs before
enabling additional symbols. Do not automatically start the six-symbol
workflow just because BTC and ETH succeed.

## Production isolation

Railway `btcusd-hourly-get-cron` has fixed watch paths covering only
production collector code and Docker inputs. No file in Phase 5 matches
those paths; merging this research PR should yield a Railway `SKIPPED`
build and should not touch the original separate 500MB persistent BTC
forward volume or modify the existing independently authorized $15 PAPER
diagnostic position. A successful GitHub history report does not prove
that Railway recorded its first genuinely prospective hourly candle.

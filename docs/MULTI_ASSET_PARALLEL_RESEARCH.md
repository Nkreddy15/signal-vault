# Phase 4 — Parallel multi-asset research, not serial seven-day waits

**Status: isolated, OFFLINE architecture and fake-fixture tests only.**
This branch/PR intentionally does NOT alter the deployed Railway BTC/USD
`--once` cron command, broker, risk limits, current persistent volume,
secret configuration, manual Mac collector or the separately authorized
one-off $15 PAPER BTC diagnostic position. Keep the first hosted BTC
prospective evidence stream stable while the broader research engine is built.

## Why this architecture is necessary

The shipped collector, strict capture/validation, EMA and backtest deliberately
hard-code BTC/USD. Those safeguards validated one end-to-end vertical slice,
not the whole desired market scanner. Serially repeating 168 observed hours
per asset would be the wrong schedule. Develop and evaluate historical models
across many predeclared candidate instruments **in parallel**; collect
genuinely prospective evidence side by side after provider access is confirmed.

A dataset of 12 assets x 168 simultaneous hours contains at most 2,016
**asset-hour rows**, but only 168 **distinct UTC clock-hours** of forward
observation. Cross-asset prices also have correlations; these rows do not
magically become 2,016 independent trading days or establish profitability.

## Initial bounded RESEARCH TARGETS (not tradability claims)

| Crypto, 24/7 UTC | US equities, session-calendar-aware |
|---|---|
| BTC/USD | SPY |
| ETH/USD | QQQ |
| SOL/USD | AAPL |
| LTC/USD | MSFT |
| LINK/USD | NVDA |
| AVAX/USD | AMD |

This is a **candidate registry**, not a statement that all listed instruments
are currently available or entitled under this Railway/Alpaca account. Query
the provider's asset/data availability first. Handle provider feeds, symbol
changes, delistings, corporate actions, holidays, DST, extended-session rules,
and incomplete last equity candles explicitly. Equity bars cannot use the
crypto assumption of 24 consecutive UTC hours. IEX-only equity bars must not
be represented as consolidated SIP prints.

`src/signal_vault/research_universe.py` defines intentionally disabled
per-instrument configs, isolated OHLCV records, immutable canonical content
SHA-256 hashes, explicit per-symbol/provider validation, and audited
parallel sample accounting. No network calls or broker components are present
in this module. Existing BTC production classes retain their BTC-only guards.

## Execution lanes (build these IN PARALLEL, no seven-day blocking step)

1. **Keep installed BTC cloud forward observer isolated and unchanged.**
   Audit the first genuinely prospective consecutive Railway close; preserve
   its own volume, segment, hash chain and source label.
2. **Historical research lane:** build rate-bounded authenticated DATA-GET
   adapters for supported crypto and separately for entitled equity feeds.
   Pull 6–24 months where actually available, with full provider/feed/source/
   timestamp manifests. Historical bars, including recent downloads, never
   count as prospective observations. Use partitioned per-instrument storage
   and immutable captures; avoid backfill masquerading as forward testing.
3. **Research strategy lane:** refactor BTC-only EMA research behind a generic
   indicator interface while keeping existing v0.1/v0.2/v0.3 immutable.
   Compare a small set of declared baselines (trend, momentum, and
   mean-reversion only where justified) with next-bar simulation, sensible
   cost assumptions, buy-and-hold/cash baselines, drawdown and turnover.
   Report gross AND net returns, and avoid selection on the test window.
   Costs differ by asset, venue, spread, market session and maker/taker tier.
4. **Independent temporal validation lane:** predeclared train/validation/
   test date boundaries per instrument, purging overlapping forward labels,
   chronological nonoverlap and a final untouched holdout. Account for
   universe-selection bias, multiple comparisons and correlated assets;
   avoid declaring an edge based on one profitable backtest.
5. **Parallel prospective shadow lane:** after provider coverage checks,
   collect supported instruments on one scheduling tick, partitioned by
   asset/venue/feed and separate immutable journals. One failed symbol must
   never fabricate data for another; missing sessions are explicitly missing.
   Paper or live order submission remains disabled.
6. **Portfolio risk lane:** future experimentation must use ONE shared logical
   research bankroll rather than giving each of a dozen strategies its own
   independent $100. Preserve existing $15 single-buy, $30 total long
   exposure, $3 session-loss and $10 drawdown research caps until separately
   revised, with per-asset and portfolio-wide maximums.

### Why we do not collect every listed market immediately

Railway's Free plan is resource-constrained, provider data permissions and
market-hour rules differ, and the present production capture is intentionally
BTC-only. Extending it in-place without a separate audit could break the first
real forward observation. The phase-4 registry/validator ships behind a
research-only boundary; data-provider adapters and batch scheduling require
their own tests before being enabled. Initial results are **research**, not
signals suitable for broker execution.

### Acceptance criteria for multi-asset activation later

- At least two candidate crypto symbols and one equity symbol have audited,
  historically captured per-feed and per-calendar datasets; no source mixing.
- Per-symbol and shared-clock prospective counts are both reported correctly.
- Every strategy receives bars only up to the decision timestamp, uses
  predeclared assumptions, and cannot call an order endpoint.
- Separate data entitlements and risk rules verified per venue; no automatic
  live/paper orders and no spurious inference from correlated samples.
- CI uses purely synthetic fixtures with no broker calls or network;
  original single-BTC tests still pass on Python 3.11 and 3.12.

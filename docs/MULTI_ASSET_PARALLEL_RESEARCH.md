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

## Phase 4 implementation details added after the initial foundation

The following modules have now been implemented on the isolated Phase 4
research branch and tested using synthetic offline-only datasets:

| Module | Implementation |
|---|---|
| `research_universe.py` | Initial 6 crypto + 6 equity/ETF disabled research candidates; canonical per-asset OHLCV/feed and explicit equity candle-grid validation; reports distinct shared UTC hours separately from total asset-hour records |
| `multi_asset_historical.py` | Fixed Alpaca `data.alpaca.markets` crypto and equity historical DATA GET paths, redirect refusal, strict symbol/query allowlists, explicit stock `iex` or `sip` with `adjustment=all`, total 1000-row page limit, page-token cycle/cap protection and no partial bundle on API failure |
| `multi_asset_simulation.py` | Same generic cash, passive, 12x26 EMA and 24-bar momentum hypotheses for any vetted asset; only prior *closed* bars decide the next OPEN; separately supplied per-market fee/full-spread/slippage, same-allocation comparator, fee-aware estimated hypothetical liquidation and 50/25/25 disjoint chronological descriptive folds |
| `shared_research_book.py` | One **shared $100** simulated portfolio, $15 single allocation, $30 combined maximum entry exposure, daily loss $3 and peak drawdown $10; same-timestamp SELLs before BUYs, deterministic allocation order, no provider account API or orders |
| `offline_multimarket_pipeline.py` | Read-only strict 0600 archived file + content-addressed name SHA validation; no historic/forward relabeling; feed-consistent nonoverlapping archival joins, source and OHLCV rechecks; per-strategy comparative folds plus shared-book EMA descriptive report |
| `multi_asset_research_cli.py` | Default zero-network/zero-credential plan, explicitly operator-triggered historically bounded download, private terminal prompts (never argv/JSON) and purely offline archive/estimated-cost report; no trading command |

Official provider API contracts consulted:
[Alpaca historical crypto bars](https://docs.alpaca.markets/us/reference/cryptobars-1),
[Alpaca historical stock bars](https://docs.alpaca.markets/us/reference/stockbars).
Alpaca documents comma-separated symbols and a **total** returned row limit
for multi-symbol stock responses: one response page may have just one asset
until `next_page_token` is consumed. Stock feed is explicitly `iex` (one
exchange) or `sip` (consolidated data); this implementation never implies
a free IEX account has SIP entitlement. The client does not access brokerage
trading/account endpoints.

### Bounded planning and isolated execution

A multi-asset historical request covers at most 14 calendar days and 1-6
same-class instruments. Up to 30 consecutive bounded windows can be planned
in one explicit invocation. A 12-instrument universe is handled as **two
separate groups** of six, crypto and stocks, because calendars, feeds,
data quality and costs differ. Full-calendar range and entitlement checks
happen before the first credentialed provider request. No downloaded
historical bar is counted as genuinely prospectively observed just because
it was fetched from Alpaca in September 2026.

For example, purely offline with no credentials or API call:

```sh
PYTHONPATH=src python -m signal_vault.multi_asset_research_cli \
  --dry-run --market crypto \
  --symbols BTC/USD ETH/USD SOL/USD LTC/USD LINK/USD AVAX/USD \
  --start 2026-03-01T00:00:00Z --end 2026-09-01T00:00:00Z
```

Actual DATA GET is separately gated by `--download-history`; its data keys
are privately requested via hidden terminal prompts and never placed in
ChatGPT, git commits, command-line arguments or filenames. Archive target
must already exist as an owner-private 0700 directory outside the persistent
production `/var/lib/signal-vault/forward` path. A failure preserves all
previously completed immutable content-hash archives without inventing a
backfill or claiming an uninterrupted capture. For equities, one must also
supply an independently **reviewed provider candle grid** per symbol and
select an entitled feed. The program refuses to guess US market holidays,
DST, partial sessions, extended-hours behavior or Alpaca's equity hourly
bar timestamp alignment.

An offline-only report requires historical archive paths and an explicit
private `--costs-file` mapping **every** instrument to modeled fee,
full bid/ask spread and per-side slippage in basis points. Example file
structure (illustrative only, NOT verified real current trading costs):

```json
{
  "BTC/USD": {
    "taker_fee_bps": "25",
    "full_spread_bps": "3",
    "slippage_per_side_bps": "10"
  },
  "ETH/USD": {
    "taker_fee_bps": "25",
    "full_spread_bps": "4",
    "slippage_per_side_bps": "10"
  }
}
```

The offline report includes net marked P&L AND estimated all-position
liquidation P&L. Those are different: an unsold holding has not paid the
future exit's spread, slippage and fee. Reported equity is approximate and
not a broker-reconciled execution. Stock cost parameters MUST be supplied
separately instead of cloning crypto taker fees. Comparisons are descriptive:
neither the later chronological holdout nor the number of candidate assets
authorizes strategy promotion.

### Production isolation and practical Free-plan limit

These Phase 4 modules are deliberately **not imported or enabled by** the
deployed Railway `btcusd-hourly-get-cron` entrypoint. Its running GET-only
BTC observer, independent 500 MB persistent volume, first zero-count
historical bootstrap, protected variables, paper-order disable flags and
Mac evidence do not change merely because research code exists in a PR.

Railway's Free storage budget is not a credible basis for retaining endless
duplicated uncompressed full-market archives. Start with bounded,
source-attributed historical samples, create checked content-hash snapshots
in an appropriate separate research environment, and estimate storage/
request costs before enabling ongoing multi-instrument hosted collection.
No parallel automatic collector, equity provider entitlement or paid hosting
has yet been activated. This is not a blocker for offline multi-asset
architecture development or simulated tests.

### Optional separate GitHub Actions historical ingestion (MANUAL only)

`.github/workflows/manual-historical-crypto-research.yml` allows a human to
trigger the first **BTC+ETH** archive download on private GitHub Actions
without giving new credentials to ChatGPT or touching Railway's production
forward volume. It has no `push`, `pull_request`, cron, live trading or paper
order trigger. It refuses any execution outside `Nkreddy15/signal-vault`
`main` + `workflow_dispatch`, checks all supplied symbols against the
predeclared crypto research universe and requires a dedicated approval flag.
It explicitly defaults to a 2026-07-01 through 2026-09-01 historical
window, two months of retrospective DATA ONLY. Download periods are split
into at most 14-day bounded API requests, six symbols maximum per group.

GitHub repository owners must privately install two encrypted **Actions**
repository secrets; do not put values in chat, code or workflow inputs:

- `SIGNAL_VAULT_RESEARCH_DATA_KEY_ID`
- `SIGNAL_VAULT_RESEARCH_DATA_SECRET`

These are an additional research workflow credential location, not a
request to expose Railway's variable values via a connector. A separate
PAPER-only data pair is preferable if the provider permits it. Some PAPER
API key pairs may still have wider venue/account capabilities despite this
GET-only application's own restrictions.

Following a manually initiated successful run, SHA-named **historical**
snapshots are retained as a private GitHub Actions artifact for **7 days**.
They are not commits, not public URLs, not genuine prospective observations
and not automatically merged into a future Railway archive. The current
private GitHub repository's Actions usage/quota should be reviewed before
clicking Run workflow. Historical GET has not been executed simply because
the workflow was committed. The stock/equity lane stays additionally gated
by explicit IEX/SIP entitlement and an independently reviewed hourly
session timestamp grid; it is not faked as 24/7 crypto.

**Production deployment isolation:** Railway
`btcusd-hourly-get-cron` was separately configured with exact SOURCE
watch paths for only its production collector, Dockerfile and direct
dependencies. Changes confined to the new Phase 4 research files,
tests, GitHub workflow and this documentation should not trigger a
Railway BTC collector rebuild. Verify the collector and volume status after
merging research code; do not assume any historical run took place.

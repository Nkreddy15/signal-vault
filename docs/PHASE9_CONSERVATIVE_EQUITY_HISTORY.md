# Phase 9 — Six US equities / ETFs, conservative historical IEX-only research

The goal is to add the **separate equities lane** alongside existing
crypto history without pretending US stocks trade 24/7 or that free IEX
equals consolidated SIP. This does NOT enable any paper/live stock order.

## Why complete CORE hours, not naive hourly stock candles?

The [Alpaca multi-stock historical bar API](https://docs.alpaca.markets/us/reference/stockbars)
offers `timeframe=1Hour`, explicit `feed=iex` and `adjustment=all`,
and **total** page size (paginate with `next_page_token`). A user report
in [alpaca-py issue #397](https://github.com/alpacahq/alpaca-py/issues/397)
describes hourly bars starting on clock-hour boundaries, NOT necessarily
from XNYS's 09:30 US Eastern opening bell. A 09:00-10:00 hourly stock bar
can then contain 09:00-09:30 premarket prints. No provider official
guarantee of hour-label alignment is assumed: the actual IEX results are
compared against an independent exchange grid, and mismatches FAIL CLOSED.

We intentionally ignore the first partial/opening bucket and any final
partial bucket. On an ordinary US summer session (13:30-20:00 UTC) the
ONLY six allowed complete 60-minute CORE buckets start at 14,15,16,17,
18,19 UTC. On the US winter half-day after Thanksgiving
(14:30-18:00 UTC), the ONLY three included buckets are 15,16,17 UTC.
The user is explicitly informed that first-30-minute opening price action
is excluded, so this research must NOT be described as complete
regular-session total return or an executable 09:30-open strategy.

The optional `exchange-calendars>=4.13,<5` package supplies source
`XNYS` sessions with relevant DST changes, holidays and early closes.
This optional dependency is installed **only** for equity-specific research
and GitHub CI, never the existing Railway BTC production collector.
XNYS is a market-hours reference; independently verify exact source bars
for NASDAQ stocks/ETFs and each selected feed. The same six-asset regular
core grid must hold for every returned IEX symbol. Missing IEX hours are
reported as a capture FAILURE, not interpolated from a stock's last price.

The [Alpaca market-data FAQ](https://docs.alpaca.markets/us/docs/market-data-faq)
distinguishes IEX's one-exchange feed from consolidated SIP. We assume
NO SIP entitlement, fetch only requested historical IEX bars, and use
illustrative fee/spread/slippage scenarios rather than representing IEX
as a consolidated live market.

## Predeclared phase-9 research set

`AAPL AMD MSFT NVDA QQQ SPY`

Default manual run covers 2026-09-14 inclusive through 2026-09-26
exclusive: ten actual XNYS sessions and 60 consecutive *session-grid*
core hourly buckets per symbol. This corresponds to **360 historical
asset-hour rows / 60 distinct clock hours**, NOT 360 independent
hours of market history or new prospective evidence. Each of the ten
individually bounded per-session `GET https://data.alpaca.markets/v2/stocks/bars`
requests must return the entire six-symbol regular-core grid on
`feed=iex`, `adjustment=all`. An IEX sparse-hour limitation may cause
a fail-closed result, which is diagnostic evidence rather than something
to paper over or justify switching to paid SIP without approval.

Workflow: `.github/workflows/manual-historical-equity-iex-research.yml`

[Open the explicit stock IEX manual workflow](https://github.com/Nkreddy15/signal-vault/actions/workflows/manual-historical-equity-iex-research.yml)

The only credentials reused are the PRIVATE GitHub Actions PAPER
historical DATA secrets previously placed by the owner:

- `SIGNAL_VAULT_RESEARCH_DATA_KEY_ID`
- `SIGNAL_VAULT_RESEARCH_DATA_SECRET`

These are injected into ONE explicit manually triggered GET-only step,
never passed as command-line arguments, printed, copied into research
bundles or shared with this conversation. Dry-run/calendar validation
happens first with zero credentials and zero API calls. No stock requests
occur just because a PR is merged; the operator must initiate this
separately scoped stock workflow. All provider calls use
`data.alpaca.markets` with an exact fixed stock-bars path and HTTPS GET;
redirects are rejected.

## Full-window archive and strategy safety

The existing source SHA-verifying archive reader now handles historical
equity sessions individually. For crypto, its prior *strict consecutive
UTC hour* requirement remains unchanged. For equities, it allows ONLY
gaps explained by the **explicit independently computed regular CORE
session timeline**, with per-session closed bars matching exactly.
Unrequested afterhours, missing buckets, overlapping stock windows,
feed mixing, duplicate/invalid OHLCV and forged prospective flags
fail closed; older archive copies are never silently overwritten.

A successful stock job creates ten private 0600 SHA-named IEX-adjusted
history snapshots plus a private `offline_equity_research.json` containing
three fixed illustrative stock-market cost assumptions and the four fixed
cash/passive/EMA/momentum hypotheses evaluated on ONE shared $100
hypothetical bankroll. There are no broker/account/portfolio calls,
automatic orders, forced liquidations, live routes or strategy promotion.

The resulting private GitHub Actions artifact expires after 7 days; save
the final complete source file into user Library before that point.
None of it automatically joins Railway's BTC cloud prospective journal.
Equity risk limits, market hour eligibility, venue minima, stocks'
fees/short-sale restrictions and realistic consolidated data all need
separate review before any paper execution would be allowed.

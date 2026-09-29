# Phase 11 — ONE operator action → historical 12-market synchronized research

**State at development:** six crypto and six US equity historical DATA sources
are individually SHA-checked, but their first captured periods are disjoint.
The July1–Sep1 six-crypto study is NOT joined to the Sep14–Sep25 stock IEX
study. Phase 11 adds a bounded source ingestion and a new strictly
**common-horizon** research simulation; real joint results do not exist
until a separately authorized overlapping six-crypto historical GET
actually completes and produces intact evidence.

## New source / evaluation contracts

`simulate_shared_research_book` has OPTIONAL global
`evaluation_start_utc` and `evaluation_end_utc_exclusive` parameters.
Both must be supplied together, timezone aware. ALL instruments must
complete their own indicator warmup before the first shared $100
hypothetical investment. The end cannot exceed the last fully closed
historic candle of the shortest observed participant (typically XNYS
stock Sep25 20:00Z, even if crypto continues overnight to Sep26 00:00Z).
Older, unscoped two/six-asset historical report schemas and replay results
remain identical: only the explicitly scoped new experiment receives
additional common-horizon provenance fields.

The pure `cross_market_joint_review.py` requires exactly six registered
crypto and six registered IEX stock/ETF candidates, the independently
verified XNYS 60-hour market-core timeline and at least 48 shared
CLOSED-hour market timestamps. Only after source quality and time
validation does it compare the original four fixed cash/passive/
EMA/momentum hypotheses under three **separately calibrated class-level
illustrative**, NOT executable, fee/spread/slippage scenarios.

Each alternative uses ONE shared $100 starting cash and $30 combined
long-only hypothetical exposure, never $100 per asset. Multiple same-clock
BUYs compete under the existing deterministic lexicographic rule; the
report records the actual subset rather than claiming all twelve coins/
stocks were bought. All stock shares are hypothetical fractional fills
until broker-supported fractional eligibility, prices, sizing and
regulatory costs are separately reviewed. A profitable short historical
simulation is never independent prospective edge or authority to trade.

`joint_historical_source.py` is a keyless two-artifact CLI. It accepts
original history ZIPs or already unpacked PRIVATE GitHub Actions artifact
folders, with size/member constraints, independently reruns:
- strict six-crypto SHA/source-archive/pagination-complete/three-cost
  historical source validation;
- strict six-stock original report SHA check for EXACT GitHub run
  **36637836735** (sha:
  `15010a1cbf376264423c5cb08cd58075c2e9d7319a74037b41d3683d819f2e6f`);
- independent ten-session XNYS CORE-hour calendar, IEX single-exchange
  full-grid and original three-cost result reproduction;
- separate immutable 0600 archive reconstructions in an ephemeral private
  folder and both original per-asset quality SHA confirmations;
- explicit no-overlap refusal before *any* combined P&L can be published;
- one shared, after-all-warmups event simulation ending at the shorter
  market dataset end; never forward-filled afterhours or pretend a
  historical source has been collected prospectively.

No external/provider network activity, new Alpaca credentials, paper
orders, stock brokerage account calls, live routes, Railway changes or
paid SIP source is introduced by the joint CLI.

## One manually requested September crypto GET; combined report AUTOMATIC

The existing GitHub workflow
[Manual multi-crypto historical DATA GET (research only)](https://github.com/Nkreddy15/signal-vault/actions/workflows/manual-historical-crypto-research.yml)
remains `workflow_dispatch`-ONLY. To align its six-crypto dataset with
the existing independently verified IEX stock source, its precise
operator inputs are:

| Input | Exact value |
|---|---|
| Branch | `main` |
| `start_utc` | `2026-09-14T00:00:00Z` |
| `end_utc` | `2026-09-26T00:00:00Z` |
| `symbols` | `BTC/USD ETH/USD SOL/USD LTC/USD LINK/USD AVAX/USD` |

The first Actions job remains the historical Alpaca DATA GET, using
the existing privately configured dedicated research DATA secrets in
ONE authenticated step. It produces source SHA archives and separate
offline three-cost crypto research, all historical. If that first job
fails or a provider returns partial data, the second job DOES NOT run.

A new second `paired-stocks-twelve-asset-offline-research` job triggers
**only** after a successful FIRST job AND those exact three manually
selected inputs. It receives no Alpaca credentials whatsoever; it uses
only read-scoped GitHub's own Actions token to download the just-created
private crypto artifact and original private historical stock artifact
from known run #36637836735. It independently reproduces the two
source archives, checks disjoint/equal clock coverage, then generates
`offline_twelve_market_joint_research.json`. The joint report is
privately uploaded to the SAME GitHub Actions run for seven days.
This makes a *single manual activation* sufficient; the user does not
need another click, Mac terminal, ZIP transfer or new account permission.

The original separately archived July/Aug crypto and September IEX stock
source datasets remain untouched. If GitHub's original seven-day
September IEX source artifact has expired, this workflow must FAIL
CLOSED instead of silently grabbing another period or assuming Library
is accessible from GitHub. The full stock original is separately
preserved in `/Signal Vault/Research/` in the user's private Library,
but no unapproved automatic migration/fetch is done.

## Expected shared-horizon constraints on these dates

When a complete Sep14–Sep26 six-crypto retrospective archive later
exists, all 60 stock CORE hour-open timestamps (Sep14–Sep25) can
fall within its continuous crypto history. The maximum **predeclared
28-bar indicator warmup** across all twelve markets implies a common
portfolio study start no earlier than XNYS's 29th
CORE-hour candle: **2026-09-18 18:00 UTC**. The earliest common
stop is **2026-09-25 20:00 UTC**, leaving just 32 stock CORE-hour
candidates after warmup; crypto also trades during nights and weekends.
This remains a SHORT, descriptive historical architecture stress test,
not a statistical validation or promotion. The actual run and report
must confirm all dates, SHA hashes and data completeness before treating
these as observations.

The Railway BTC-only prospective hourly GET cron is not imported or
modified by these offline modules; the stock workflow is not scheduled,
and the user's original isolated prospective count remains distinct.

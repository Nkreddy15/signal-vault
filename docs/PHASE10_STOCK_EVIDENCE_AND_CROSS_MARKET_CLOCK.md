# Phase 10 — Independent real-stock source replay & 12-market time-alignment gate

The owner's manually initiated historical IEX run
[36637836735](https://github.com/Nkreddy15/signal-vault/actions/runs/36637836735)
finished successfully on 2026-09-29. The original PRIVATE Actions artifact
is named `historical-6-equities-IEX-core-hours-36637836735`; it was
downloaded with SHA-256
`08223c1159390a7e6c460be005059031cf48fd7c847f1d059a3898cc49d7e5e4`,
exactly matching the Actions artifact digest. A duplicate of that ORIGINAL
archive is preserved in the user's Library:

`/Signal Vault/Research/2026-09-29_six-stock_IEX_core-hour_original_history.zip`

The ten individual 14:00–20:00 UTC IEX regular-core session JSON
source archives independently match their stored SHA digests, and the
`offline_equity_research.json` SHA is
`15010a1cbf376264423c5cb08cd58075c2e9d7319a74037b41d3683d819f2e6f`.
There are exactly 60 closed hourly candles per AAPL, AMD, MSFT, NVDA,
QQQ and SPY, 360 **asset-hour records** but only 60 unique observed
stock-market clock hours. The first 09:30–10:00 US Eastern partial
regular-session opening bucket is deliberately omitted. `feed=iex` and
`adjustment=all`: this is single-venue IEX, not entitled consolidated SIP
and NOT 24/7.

## What the stock simulation actually tested

The fixed v2 risk/cost-aware hypothetical $100 shared-book results,
including *modeled closing costs*, were:

| Hypothesis | Illustrative low stock friction | Base | High |
|---|---:|---:|---:|
| Cash | $0.00 | $0.00 | $0.00 |
| Generic EMA12x26 | -$0.15 | -$0.19 | -$0.30 |
| Generic 24-bar momentum | +$2.56 | +$2.54 | +$2.46 |
| Passive allocation | +$2.56 | +$2.54 | +$2.46 |

IMPORTANT: momentum and passive in THIS PARTICULAR tiny stock sample
both generated exactly TWO $15 hypothetical fraction-of-share BUYs at
2026-09-18 18:00 UTC, **AAPL (approximately 0.04467 shares) and AMD
(approximately 0.02748 shares)**, with no subsequent SELL. They are
not independent confirming signals or evidence the strategies beat one
another. The default deterministic alphabetical allocation and $30
combined-long cap forbid claiming a diversified six-stock investment.
EMA generated five hypothetical MSFT fills. Fractional-stock eligibility,
actual trade permissions, venue minima, spread, regulatory fees and
realistic execution are **not** provider verified: the simulator cannot
place an actual stock/PAPER/LIVE order.

A 60-bar sample with a 28-bar indicator warmup leaves only **32**
evaluated bars (16 development, 8 validation, 8 untouched test).
These disjoint descriptive folds are far too small for strategy selection,
a risk forecast, or performance promotion. Values above are historical
*illustrative* after-cost calculations, not financial advice or returns.

## Independent stock artifact audit

`src/signal_vault/offline_equity_zip_audit.py` is a keyless/no-network
source-verification module. It reads the private original ZIP with bounded
decompression and strict flat-member filename/symlink/size rules, checks
all original day digests, reimports only the verified stock archive bytes
into a temporary owner-private 0700 folder, and runs the strict canonical
historical batch reader. It independently regenerates XNYS core-session
boundaries (including calendar DST, holiday and early closes) and requires
each provider IEX adjusted session and all six symbols to match **exactly**
before joining the ten source batches.

The auditor recalculates all four fixed hypotheses under all three
explicit illustrative stock-friction scenarios and requires exact
source-report equality. Tampered source files, adjusted assumptions,
missing exchange dates, wrong bars, ZIP traversal and fabricated trade
permissions FAIL CLOSED, without altering the original history.
SHA matching verifies local archive reproducibility, not an external
cryptographic provider signature.

From a checked-out source tree with optional `[equity-research]`
dependency installed, e.g.:

```sh
PYTHONPATH=src python -m signal_vault.offline_equity_zip_audit \
  --source-zip /private/path/six-stocks-original.zip \
  --output /private/new/iex-source-audit.json
```

No Alpaca credentials, account, Keychain, Railway volume, network request
or order subsystem are imported or used by this ZIP audit.

## A critical blocker to claiming a 12-market combined test

Our existing six-crypto historical archives cover **2026-07-01T00:00 UTC
through 2026-09-01T00:00 UTC (exclusive)**. The first six-stock IEX
archives start **2026-09-14T14:00 UTC**, ending Sep25 20:00 UTC.
Those studies have **zero common historical UTC candle hours**.

Consequently the individual $100 crypto and stock results CANNOT be
added, ranked together as one contemporaneous experiment, or described
as a measured twelve-asset portfolio. The new pure
`historical_clock_overlap.py` reports verified source clock intersection
and refuses to label a mixed-calendar dataset even BASIC aligned when
fewer than 48 historical stock regular-core candle timestamps match a
closed crypto hour. Even a full match is only a TIME-COVERAGE prerequisite,
not a combined portfolio run or trading evidence: first align a common
evaluation start, pre-event indicator warmups and a single shared account
book with two independently sourced calendars.

**Next human-only provider step after review (NOT auto-launched):** the
existing GitHub manual historical crypto workflow can be run with its
six-coin choice and historical dates
`2026-09-14T00:00:00Z` to `2026-09-26T00:00:00Z`.
This permits calendar overlap with all 60 stock core-hour timestamps,
without changing the production forward collector or requesting any SIP
feed. Those would remain retrospective GETs, never genuinely prospective
new observations. Do not claim successful overlap until that next source
download actually runs, is SHA checked and independently compared.

All Phase 10 additions are offline research modules and tests. The
Railway BTC collector uses a different entrypoint, fixed watch paths
and an independent 500 MB persistent volume. No trading permission,
cost commitment or automatic new provider request is introduced.

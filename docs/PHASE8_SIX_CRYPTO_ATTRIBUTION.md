# Phase 8 — Six-market history, passive basket attribution and source-zip audit

## Verified external historical input

The owner manually started GitHub Actions run
[36635723718](https://github.com/Nkreddy15/signal-vault/actions/runs/36635723718)
on 2026-09-29, AFTER the Phase 6 corrected UTC daily/peak risk model and
Phase 7 exact-signal-parity linear-time simulation merged. Its output is
one owner-private, **historical-only** GitHub Actions archive containing:

- Six crypto candidates: AVAX/USD, BTC/USD, ETH/USD, LINK/USD, LTC/USD, SOL/USD.
- Inclusive start 2026-07-01T00:00Z and exclusive end 2026-09-01T00:00Z.
- Each symbol has exactly 1,488 contiguous CLOSED hourly candles; 8,928
  historical asset-hour observations in total, but only 1,488 distinct
  shared clock hours; **ZERO** are a new forward/prospective capture.
- Five bounded historical archives SHA-verified against the report.
- The complete original six-market ZIP checksum:
  `848c42acdc7346e4c57ebffbcbb771612bb53fda54db45cc6e8e6cd07ead73d7`
  (the GitHub Actions artifact digest matches this downloaded ZIP).
- Original analysis-report SHA:
  `900b657b13d6b197699182e1a9f39332bd7d112125f02148b0bc5fef48d775bc`.
- Comparing the independent prior two-market run to the six-market source,
  all 1,488 BTC/USD and all 1,488 ETH/USD bar OHLCV/source/timestamp
  records agreed exactly after removing the different *download* times.

The source archive was independently preserved in user Library:
`/Signal Vault/Research/2026-09-29_six-crypto_original_historical_research.zip`.
This is separate from the GitHub Actions artifact, which expires after
seven days. Neither item is a signed provider attestation or proof of alpha.

## Why the passive benchmark needed another audit

The existing historical comparison runs four fixed strategies under ONE
shared hypothetical $100 bankroll, with a $15-per-entry and $30 total-long
cap. Under deterministic alphabetical simultaneous-entry processing,
a 'passive' allocation selects **AVAX/USD + BTC/USD**, NOT a six-coin
equal-weight investment. It leaves $70 in cash. The positive full-period
passive scenario is therefore NOT a claim about six-asset diversification
or recommendation to choose AVAX/BTC.

`universe_attribution.py` now enumerates *every* two-asset passive
alternative of the exact same $15 + $15 hypothetical capital, same next
opening candle, same final closed mark and separately provided per-asset
illustrative taker fee/full spread/slippage. Six assets generate 15 pairs;
these are **alternative counterfactual experiments**, not concurrent
$100 portfolios, a strategy-selection leaderboard or 15 independent
probability samples. It also reports descriptive same-hour close-to-close
Pearson correlation for each pair using precisely the aligned 1,487
return-hour observations; correlation is not predictive.

`offline_zip_attribution.py` consumes the private GitHub ZIP with ZERO
network and ZERO credentials. It rejects zip-slip/symlink/unknown members,
excessive sizes, unknown cost models, missing or SHA-mismatched source
archives, unsupported schema/market/version, incomplete plan windows,
mixed feeds and fabricated prospective flags. It reconstructs all six
private 0600 archive files inside an ephemeral 0700 temporary folder,
then reuses the existing strict historical archive reader and joint
quality validator. For **each** low/base/high estimated cost scenario,
the alphabetical first-pair result MUST reconcile exactly (Decimal P&L)
with the original shared-passive published result; a mismatch stops the
whole audit rather than inventing an interpretation.

From a local checkout with the preserved private ZIP available:

```sh
PYTHONPATH=src python -m signal_vault.offline_zip_attribution \
  --source-zip /private/path/six-crypto-history.zip \
  --output /private/new/0600-report.json
```

The output JSON is a new create-only file. It states sources, 15 pair
alternative results under three illustrative fee/slippage scenarios,
pairwise descriptive correlations and explicit no-new-trade/no-validated-
edge flags. The ZIP is read-only and neither Railway's persistent forward
volume nor any PAPER position is accessed.

## Historical six-market v2 result interpretation

On the one shared simulated $100 and **estimated exit-inclusive** P&L:

| Hypothesis (predeclared) | Low friction | Base friction | High friction |
|---|---:|---:|---:|
| Cash | 0.00 | 0.00 | 0.00 |
| Generic EMA 12/26 | -2.88 | -6.33 | -10.05 |
| Generic 24-hour momentum | +2.07 | -2.80 | -8.37 |
| 'Passive' (first alphabetical AVAX + BTC pair only) | +5.35 | +5.24 | +5.03 |

Every number is an **historical illustrative backtest**, not realized
broker fills, current market friction, a trading recommendation or a
prediction. High-friction EMA and momentum each tripped the simulation's
durable peak-drawdown entry halt; no provider order or liquidation was
sent. The untouched chronological folds must not be mined to select a
new asset or parameter after seeing them.

## Production isolation

These Phase 8 modules are offline and not imported into any deployed
Railway production BTC collector or trading entrypoint. Railway's
specific watch paths exclude all Phase 8 files. The original independently
operating hourly BTC GET-only production forward collector remains
unchanged, as does its own prospective record count and immutable evidence.
A separate stock research lane needs market-session-aware provider/entitlement
checks before historic US equities can be treated as comparable to 24/7
crypto.

# REGIME-SWING-LAB-1: actual development replay assessment

Evidence: user-uploaded `regime-summary.txt`, October 3, 2026. March 1 through
June 30, 2026; each continuous scenario starts at $100. Results include modeled
fees, spread, slippage and synthetic-short carry; operating costs were zero.
The replay source and shared-engine hashes match the published build.

**Rejected: no scenario passes the development screen.** No activation or
change to paused paper entries is justified by these results.

| Group | Best ending equity | Profitable scenarios |
|---|---:|---:|
| Kraken fees, cash-funded long only | $96.79 | 0 / 16 |
| Kraken fees, synthetic long/short | $97.36 | 0 / 16 |
| Lower-fee sensitivity, long only | $97.59 | 0 / 16 |
| Lower-fee sensitivity, synthetic long/short | $100.54 | 2 / 16 |

The $100.54 scenario is `leader_7d-aggressive-synthetic_long_short-`
`alpaca_rate_sensitivity-15bps-trigger`: 67 trades, profit factor 1.016,
maximum drawdown 11.23%, one positive independent month out of four and
median independent monthly return -1.90%. This is neither a demonstrated
edge nor evidence that Alpaca can execute the synthetic shorts or those assets.
The two profitable scenarios are alternative execution assumptions for the
same setup, not independent successes. No $250 or higher monthly milestone
was reached. All 64 scenarios took trades.

Every Kraken long-only scenario has negative gross recorded-fill P&L before
explicit fees. Lowering explicit fees alone cannot repair those particular
entry/exit paths. Gross fill P&L still includes modeled spread and slippage;
it is not a frictionless market-return estimate. Altering fees also changes
stakes, trade eligibility and subsequent account paths.

## Coverage and exits need investigation before another strategy iteration

The frozen universe contains 24 assets; only 16 have any completed days after
the 29-day uninterrupted warmup. FARTCOIN, NIGHT, WIF, BCH, USELESS, XPL,
PENGU and PUMP have zero eligible days. Their bars were preserved, but they
could never generate daily signals in this build. Strict complete-day
requirements and restarting indicators after every incomplete day substantially
reduce the usable sample. This is not permission to silently fabricate missing
bars or select only the winners after observing their returns.

The best Kraken long-only setup closed 19 positions, 18 on rank exits;
median holding time was 48 hours. Its gross fill P&L was -$1.07 and explicit
fees $2.14. The retention rule still caused frequent exits. Full candle and
trade evidence is required to distinguish market weakness, changing ranks,
coverage resets and the effects of execution assumptions.

## Export the existing evidence once

```bash
bash trading_stack/export_research_mac.sh
```

This builds the research image, reads the cached frozen-universe candles and
the completed replay, and places `signal-vault-research.zip` in Downloads.
It does not rerun strategies, restart paper services or change entry pauses.
The ZIP contains lossless normalized CSV candles, the formation universe,
all 64 scenario JSONs (fills, equity curves and monthly account results),
exact replay engine sources and a checksum manifest. Files are selected by
an explicit list; credentials and unrelated files are not collected.
The exporter rejects stale candle hashes, changed replay engines or incomplete
ledgers and verifies the ZIP before writing it. The ZIP is limited to 30 MiB.

Upload it through the attachment button. Research can then run directly against
the actual data in the development workspace, rather than requiring a Mac
command and summary upload for every hypothesis. Loading needs pandas/numpy
but not Feather or pyarrow:

```python
from export_research_bundle import load_bundle
frames, universe, manifest = load_bundle('signal-vault-research.zip')
```

The CSV reader preserves floating-point round trips. Original gaps stay intact.
Checksums establish internal consistency, not independent data authenticity.
All these dates remain reused development data. A profitable backtest found
while iterating over them will require separate validation.

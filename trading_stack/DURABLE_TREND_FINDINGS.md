# Actual cached-candle research: October 3, 2026

**No executable profitable bot has been established. Paper entries remain
paused.** This build corrects a data-interpretation mistake and identifies a
weak synthetic-short research hypothesis. It does not activate any strategy,
submit orders or promise a return.

## Evidence and reproducibility

The uploaded `signal-vault-research.zip` passed its member checksums and
normalized-candle validation: 24 formation-selected USD assets, 412,086 observed
15-minute candles, January 1 through June 30, 2026. Selection was fixed from
January 1–7 liquidity. Account experiments cover March–June and start at $100.
No later winning asset was manually selected.

Two original strict-coverage scenarios were independently replayed. Their
equity, trade count, pairs, entry/exit timestamps and exit reasons matched the
uploaded original ledgers. The results were $96.79208812545725 on 19 trades
and $87.79178158973006 on 31 trades. CSV transport did not explain the failures.

We then ran 64 corrected original scenarios, 64 fixed durable scenarios and
12 post-selection cost sensitivities. `research_results/20261003_daily_replay/`
contains all scenario summaries, inputs/source hashes, original replay checks
and the complete weekly candidate trade ledger. All 37 mechanics/transport
checks passed; these tests establish software behavior, not market returns.

## Archive interpretation fixed

[Kraken documents](https://support.kraken.com/articles/360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data)
that its historical archive contains only intervals with trades. Our previous
96-observed-bars-per-day requirement incorrectly treated omitted no-trade
intervals as unusable daily history. Frequent omissions repeatedly reset the
29-day warmup, leaving eight selected assets with no eligible daily signals.

V2 aggregates observed OHLCV after the UTC day closes. It uses no fabricated
execution bars or quotes. Wholly absent days still reset indicators. The fill
engine still waits for an observed asset quote. All 24 assets now have usable
daily history. This source-specific interpretation is not a repair policy for
missing live-feed data.

The corrected original hypotheses **still lose in all 64 scenarios**. The
best Kraken cash-funded long-only scenario ends at $96.33; the best synthetic
Kraken case ends at $97.43. Correcting coverage was necessary; it did not
create an edge.

## Three fixed holding-rule hypotheses

After seeing the corrected failure, we specified these changes before their
replay. They remain additional tests on already-used development data.

| Hypothesis | Entry and exit |
|---|---|
| `trend_hold_28d` | Original top-two 28-day leader entry; retain until EMA21 direction breaks rather than rank loss |
| `weekly_leader_28d` | Original top-two entry/top-four retention reviewed at Monday UTC close; resulting orders first eligible Tuesday opening quote |
| `channel_28d` | Break previous 28 daily highs/lows with EMA21 direction confirmation; retain until EMA21 direction breaks |
| `blend` | All three compete for one account; one position per asset and 50% family allocation limit at entry |

Each uses the same 6–20% daily-ATR stop distance, causal trailing rules,
1%/3% risk budgets, exposure limits, $5 minimum simulated stake and account
drawdown triggers. Maximum hold is 56 days. Stops and risk/time exits apply
on observed 15m bars even for weekly reviews. No profit target or account
profit ceiling is added.

## Results: modest synthetic gains, no cash-funded winner

| Group | Best ending equity | Positive scenarios |
|---|---:|---:|
| Kraken fees, long only | $98.42 | 0 / 16 |
| Kraken fees, synthetic long/short | $103.85 | 4 / 16 |
| Lower-fee sensitivity, long only | $98.39 | 0 / 16 |
| Lower-fee sensitivity, synthetic long/short | $113.75 | 6 / 16 |

The largest gain is weekly/aggressive/lower-fee/trigger: 33 trades, profit
factor 1.506, maximum drawdown 13.01%, and median independent monthly return
2.685%. The extrema case ends at $112.86, PF 1.468 and DD 13.21%.
Trigger has three positive independent months; extrema has only two of four.

Under Kraken fees, that weekly aggressive setup ends at $103.85 (trigger) or
$102.74 (extrema); PF 1.131/1.092; DD 14.54%/14.72%; only two positive months
in both cases. No setup passes the existing Kraken long-only screen. The
synthetic cases cannot promote a spot bot regardless of their returns.

The lower-fee trigger's long trades lose $1.19 and shorts gain $14.94 after
their modeled costs. The Kraken trigger's longs lose $6.36 and shorts gain
$10.22. Removing the losing direction after seeing this breakdown would be
another post-selection hypothesis, not validation.

The lower fee is an Alpaca-rate sensitivity on Kraken prices; it is not an
Alpaca execution result. [Alpaca crypto cannot be sold short](https://docs.alpaca.markets/us/docs/crypto-trading).
Kraken offers a separate eligible-US-retail margin product, but its supported
pairs, opening charges, dynamic four-hour rollover rates and margin/liquidation
mechanics are not this synthetic model. See [US margin](https://support.kraken.com/articles/getting-started-us-margin)
and [US margin fees](https://support.kraken.com/articles/us-margin-fees).
Neither account eligibility nor executable asset support has been established.

## Post-selection execution and operating-cost stress

The weekly aggressive candidate was selected from the preceding experiment.
These additional sensitivities are explicitly post-selection diagnostics,
not independent validation. The initial model uses 15bps spread, 0.10%
slippage each side and assumed synthetic-short carry of 0.03% daily.

| Assumption | Kraken trigger / extrema | Lower-fee trigger / extrema |
|---|---:|---:|
| Original modeled execution | $103.85 / $102.74 | $113.75 / $112.86 |
| Spread 30bps; slippage 0.20% each side | $102.22 / $101.47 | $111.73 / $110.70 |
| Above plus hypothetical $0.10/day operation | $87.49 / $86.54 | $92.17 / $91.10 |

$0.10/day is an illustration, not a measurement of the user's bill. It charges
$12.20 over 122 days, including cash days. Costs alter stake eligibility and
subsequent trade paths, so results cannot be obtained by simply subtracting
$12.20 from the no-cost ending balance. Actual running costs, historical
borrow availability/rates, broker fills and liquidation remain unverified.

The evidence supports testing weekly turnover reduction further. It does not
support 25–30% daily returns, $100-to-$1,000 monthly growth, or deploying a
margin bot. Reused development data and 33–34 trades are a weak basis for a
profitability claim. New venue-native data and a frozen specification are needed
before assessing generalization.

## Run directly against the portable archive

With pandas and numpy installed and `signal-vault-research.zip` available:

```bash
PYTHONPATH=trading_stack/crypto python trading_stack/crypto/regime_swing_lab.py --bundle signal-vault-research.zip --output-dir research/regime-v2
PYTHONPATH=trading_stack/crypto python trading_stack/crypto/durable_trend_lab.py --bundle signal-vault-research.zip --output-dir research/durable-v1 --stress
```

Docker Desktop can reproduce the cached durable research with
`bash trading_stack/research_durable_mac.sh`. No new Mac run is needed to
review the committed results; the uploaded data was already replayed here.
The old Mac regime runner now writes `regime-swing-v2`, preserving V1.
An optional later export can specify its result folder, for example
`bash trading_stack/export_research_mac.sh durable-trend-v1`. Completed runs
snapshot exact strategy, runner and accounting code for future exports.

# Cost-aware forecasts and a broader opportunity universe

The reported 80 fixed multi-strategy configurations all lost money in their
continuous H1 runs. None passed their development screen. This release changes
the research approach and retains those failures for diagnosis. It does not
activate another unproven paper engine.

**There is no $1,000 or other account-profit ceiling.** The old $1,000 field was
a measurement milestone. Equity-based sizing compounds retained capital. Risk
triggers, position stops, trade targets and time exits still apply; removing
those is not a substitute for finding an edge. New reports measure several
milestones through $10,000 without stopping at any of them.

## Run on the Mac

In GitHub Desktop fetch/pull `phase-162-multimarket-reset`, then run from the
existing repository with Docker Desktop running:

```bash
bash trading_stack/research_edge_mac.sh
```

This builds a separate, ephemeral research image with pinned scikit-learn
1.9.1. It leaves the running containers and paused-entry markers intact.
It reads the existing 80 detailed reports to export cost attribution first,
then reads the cached Q1/Q2 ZIPs to prepare the broader data universe and run
forecasts. Cached archives are reused. If an archive is missing, the existing
public archive downloader can fetch it. No keys or order endpoints are used.

It produces:

- `.data/edge-research-v1/prior-strategy-audit.md`: recorded gross returns,
  fees, carry, reconciliations, exits, benchmarks and prior selectors.
- `.data/edge-research-v1/forecast-results.md`: the new 48 scenario outcomes,
  with ending/peak equity, trade counts, recorded-fill gross, fees, drawdowns
  and median monthly return.
- `.data/edge-research-review.zip`: both JSON summaries and readable reports,
  packaged for review without copying a large terminal log.

Detailed results stay in the existing Docker volume at `edge-research-v1`;
data and the selection manifest stay under `edge-universe-v1`. If a later step
fails, the prior cost-audit files have already been copied locally.

An optional power/connectivity/subscription estimate is deducted from every
simulated account, including periods holding only cash:

```bash
bash trading_stack/research_edge_mac.sh --daily-operating-cost-usd YOUR_ESTIMATE
```

Replace `YOUR_ESTIMATE` with a nonnegative dollar amount. It defaults to zero,
because actual running costs are unknown. A dollar of simulated trading profit
is not necessarily a dollar of economic benefit.

## Separate costs from the failed strategies

The audit reads existing fills without replaying them. For completed accounts,
it checks that recorded-fill gross minus fees, short carry and operating costs
reconciles to net realized P&L. It also shows exit reasons and holding duration.
Recorded-fill gross already incorporates spread/slippage in fill prices.

Adding fees back is **attribution**, not a zero-fee backtest. Removing fees
would change account equity, sizing, tier eligibility and loss-trigger timing.
The audit therefore does not promote such an added-back number as a strategy
that can be executed without costs. Missing detail files and pending end
positions are explicitly reported.

## Select the opportunity universe before testing returns

The preparer discovers exact USD/15m markets in the Q1 archive, excluding an
explicit list of fiat, stablecoin, gold and leveraged-token symbols. It selects
up to 24 assets by median daily dollar volume measured **January 1–7 only**.
Formation coverage must be at least 90%, positive-volume bars at least 70%,
and median daily volume at least $100,000. No subsequent return enters the
ranking. The size can be set with the `EDGE_UNIVERSE_COUNT` environment variable.

The chosen set is frozen for these experiments. A selected asset missing from
the Q2 archive stays selected; its later absence is recorded. It is not removed
because it failed to survive. Missing bars are not manufactured. Indicators
restart after every gap. Historical archive completeness may still omit some
delisted markets, so this is not a guarantee that all survivorship bias has been
removed. USD archive availability also does not establish a future broker's
supported asset list or real liquidity at the modeled fill size.

## Forecast net trade payoffs with chronology enforced

Decisions use the last closed 15m candle of each hour. Features are backward-
looking 1h/4h/24h/72h returns, ATR, directional strength, RSI, EMA relationships,
range position, relative volume and time of day. Features use each asset's own
history; there is no future full-sample normalization or random train/test split.

Each historical label represents an independent **long** trade entered at the
following bar's modeled ask plus slippage. Stops use three prior ATRs, bounded
at 2–8%; targets are three stop distances, bounded at 6–24%; maximum hold is
48h. There is no trailing stop for these forecast labels or positions. Labels
use normal trigger fills with adverse opening gaps and stop-first ambiguity,
plus actual entry/exit-notional fees and adverse slippage. A label crossing a
missing candle or a rejected opening-price drift is unavailable.

Before each calendar test month:

1. Use at most 90 days of past training rows. Every training label must have
   fully completed **before** the 14-day calibration period begins.
2. Fit a standardized Ridge regression and a histogram gradient-boosted tree
   model. Scaling is fitted on training rows only; boosted random early-stopping
   splits are disabled. Both models have fixed settings and deterministic seeds.
3. Calibrate four fixed predicted-net thresholds (0.3%, 0.6%, 1%, 2%) using
   completed outcomes from the earlier calibration period only. Selected events
   are spaced by a full label horizon within each asset. Require at least 30
   such events, average after-cost return at least 0.3%, and profit factor at
   least 1.1 when losses exist. Cross-asset dependence remains.
4. Test the following month with that frozen fit and threshold. Insufficient
   history or unsuccessful calibration opens no new forecast positions.

Three arrangements are evaluated: Ridge, boosted trees, and consensus using
the lower prediction from the two models. The consensus requires both to exceed
its calibrated threshold. Signals rank by predicted net return per stop
distance. Forecast output is an estimate, not a promise of realized profit.

Independent single-trade labels do not incorporate portfolio drawdown halts,
cash contention or correlation. The shared-account replay applies those rules,
so actual portfolio exits can differ. Fold receipts include training hashes,
maximum label-availability times and the first test forecasts. They make the
training/calibration chronology reviewable.

The earliest normal test month is expected to be March after formation,
indicator warmup and minimum past-history requirements. Calendar-month trials
reset independently to $100; the continuous test account carries equity across
test months. Neither resets after a profit milestone. The default replay
compares 48 scenarios: three model arrangements, two risk profiles, two fee
scenarios, two spreads and two execution models. It remains long-only and
fully cash collateralized; no leverage is modeled.

## Verify execution economics explicitly

Kraken spot scenarios use the verified schedule and simulated rolling volume,
beginning at 0.80% taker per side. Another scenario uses Alpaca's verified
0.25% entry-tier taker rate and its published tier thresholds. **The latter is
only a fee-rate sensitivity on Kraken data.** It does not establish equivalent
Alpaca quotes, fills, asset eligibility or credited-asset fee accounting. Moving
to another venue would require native market data and a verified adapter.

Training labels conservatively use the scenario's entry-tier rate and 15bps
spread. Replay fees may improve only when its own filled volume earns a tier.
Replay spreads are 5/15bps and slippage is 0.10% per side. No free, guaranteed
maker or leveraged fills are assumed. Compare normal trigger execution with
extrema stress execution. Both remain approximations of unknown intrabar
liquidity and quote polling.

Balanced/aggressive position-risk budgets remain 1%/3%; peak-equity drawdown
triggers are 25%/50%, and daily triggers 10%/20%. Allocation is at most 80% at
entry, with cash reserved per position and capacity increasing with equity to
six simultaneous assets. These are research scenarios. Gaps and missing data
can cause larger losses. There is no account profit target that turns the
engine off or withdraws money.

## Development decision and evidence limits

The fixed development screen requires at least three complete test months,
20 trades, positive continuous and median-month returns, at least 60% positive
months, profit factor at least 1.1, drawdown within the profile's trigger and
no pending positions. A robust Kraken development candidate must pass all
four spread/execution combinations. Passing an Alpaca-rate scenario is listed
separately as a sensitivity result and cannot qualify a Kraken candidate.
No historical winner is automatically activated.

Q1/Q2 have already influenced development, and previous experiments were
numerous. Chronological fitting protects against future-label leakage; it does
not undo prior dataset reuse or selection bias. A passing candidate still
needs a frozen specification, untouched venue-native data and prospective paper
execution. This release establishes no profitability or tenfold-growth claim.

Tests cover formation-only selection, stablecoin/exact-market matching,
retention of later missing assets, label/engine cost reconciliation, entry
drift, missing forward candles, label-availability purging, calibration event
spacing, future-price invariance of model fits/first forecasts, all 48 reporting
scenarios and equity above reporting milestones. Generated prices are fixtures.
The build workspace lacks the actual archives and Docker; Mac execution must
verify the package download, full archive coverage and real replay. Runtime
library versions are recorded; the research image pins scikit-learn 1.9.1.

## Primary sources

- [Cost-aware walk-forward forecasting preprint](https://arxiv.org/abs/2606.00060): evidence that forecast-to-trade conversion and costs matter; its performance is not imported as our performance.
- [Temporal split and gap documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html).
- [Histogram gradient boosting documentation](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html).
- [Alpaca crypto fee schedule](https://docs.alpaca.markets/us/docs/crypto-fees).
- [Kraken fee schedule](https://support.kraken.com/articles/cross-platform-fee-tier-changes).
- [Pinned scikit-learn package](https://pypi.org/project/scikit-learn/1.9.1/).

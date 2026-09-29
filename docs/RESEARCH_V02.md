# Signal Vault v0.2 — predeclared DEVELOPMENT experiment

**Status: OFFLINE RESEARCH ONLY. Not enabled in the paper worker or daemon.**
This document fixes the hypothesis before the first v0.2 empirical run on owner-captured data. It is not an approval to trade.

## Evidence available before candidate construction

- Alpaca PAPER authenticated read-only account and BTC/USD quote checks passed locally on the owner's Mac; no keys or authenticated data are checked in.
- Four genuine UTC hourly CSVs were captured and owner-verified by SHA-256; the files live **only on the owner's Mac**, not in GitHub. One missing March 12, 2026, 17:00 UTC hourly bar was confirmed directly from the Alpaca crypto data API. The two contiguous segments are never bridged by interpolation or an unrecorded synthetic candle.
- Development CSV: `data/research/btcusd_older_pregap.csv`, strictly December 25, 2025 22:00 UTC through March 12, 2026 17:00 UTC exclusive, 1,843 hourly observations, SHA-256 `0f31fa3e6226a504db4b60185ae7388ae8979c14e3ccef1fc1b98e2b809071cc`.
- On this development segment, the baseline v0.1 completed 33 trades (7 profitable, 26 losing); median holding time 16 hours; 67 fills including an open position. Baseline P&L was -$4.9129 with modeled costs and -$1.4142 without costs. This history **is already examined and is not an unseen holdout**.
- The previously examined v0.1 June–September 90-day dataset and September seven-day dataset cannot be relabelled as independent unseen tests.

## Single v0.2 hypothesis (fixed in advance)

Test whether waiting for a **second consecutive strictly positive fully CLOSED hourly state of the 12-hour EMA above the 26-hour EMA** after the actual upward crossover reduces unproductive buys.

Exactly these changes are allowed in v0.2 compared to v0.1:
1. A v0.1 BUY signal on the first positive closed bar becomes HOLD.
2. At the next hourly close, BUY is emitted **once** only if fast EMA remains strictly greater than slow EMA and the prior bar was the first positive one.
3. Any confirmed bearish EMA crossover retains the **original immediate SELL** timing. No extra confirmation is required for sells.
4. Otherwise HOLD. Do not turn a HOLD/SELL into a BUY from ML or a forecast.

Everything else is unchanged: 12/26 EMA; next-open hypothetical fills; one position; no shorts or leverage; $100 logical bankroll; $15 buys; existing Guardian; 0.25% assumed taker fee plus 0.10% slippage per side; $10 assumed venue minimum. The cost assumptions are hypotheses, not audited actual fills. No discretionary stops or additional thresholds are tuned.

## Experiment design

Run `PYTHONPATH=src python -m signal_vault.research_v02` **only** in the owner's local checkout. It first checks the exact predeclared SHA-256, number of observations and boundaries; then reports v0.1 and v0.2 on the same pre-gap development sample, each under both costed and zero-cost models. No other CSV is opened; no network requests, credentials or paper-order endpoints exist in the experiment module. Compare P&L, passive same-allocation benchmark, estimated fees, fill count and maximum drawdown. Do not claim statistical evidence of positive edge based on a single development sample.

After reviewing results, either reject the candidate or **freeze** the candidate's code, dataset boundaries, cost assumptions and risk settings. Only after that review may a new candidate be evaluated on a truly reserved time segment. For stronger independent inference, obtain genuinely future hourly observations after the last previously examined data, as the previous 90-day holdout was already exposed in the v0.1 diagnostic.

No activity in this research workflow enables a broker order, a cloud service, live mode or a deposit.

## Observed first development run — owner-reported 2026-09-28

The owner ran the predeclared command on the exact SHA-verified development CSV above. All values below are **offline/hypothetical**, not provider fills or broker PAPER performance.

| Metric | v0.1 baseline | v0.2 two-bar confirmation |
|---|---:|---:|
| After-cost net P&L on reset $100 | -$4.91289611 | -$4.90227649 |
| Zero-cost net P&L | -$1.41415883 | -$1.66739272 |
| Estimated fees | $2.50355228 | $2.31562713 |
| Simulated fill count | 67 | 62 |
| Maximum drawdown after costs | $5.58196494 | $5.57696992 |
| Marked open BTC at dataset end | Yes | No |
| Same-allocation passive BTC comparator | -$3.00429615 | -$3.00429615 |

The v0.2 model produced about **$0.01062 less negative** after-cost P&L but **$0.25323 more negative** zero-cost P&L, with 5 fewer fills and approximately $0.18793 fewer estimated fees. Open-position statuses differ, so these endpoint comparisons are not paired completed-trade treatment effects.

**Disposition: Do not promote v0.2 to provider-paper shadow or order execution.** Both variants remain loss-making on this development sample, and the apparent costed difference is not meaningful evidence of predictive advantage. Preserve v0.1 and v0.2 code plus this record as fixed, evaluated research artifacts. Do not open the post-gap reserved dataset merely to rescue either variant. No future holdout result has been observed for v0.2.

## Next research stage

Perform **descriptive attribution**, not another ad-hoc parameter sweep. Investigate losing trade size/distribution, entry-to-exit timing, trend versus range regimes, and gross-versus-cost effects using the already-exposed pre-gap development sample only. Make no claim of an edge or promotion while both fixed variants fail. If a distinct v0.3 hypothesis is justified, preregister and version it before running it, limit candidate search, and reserve genuinely prospective observations (after the last previously inspected period) for independent testing. Paper POST, live, funding, deployment and spending remain disabled.

## Completed trade-duration diagnostic (owner-reported 2026-09-28)

The owner ran `PYTHONPATH=src python -m signal_vault.research_attribution` on the same SHA-verified 1,843-bar pre-gap development CSV. Both strategy versions produced `reconciliation: PASSED` for full marked-to-market net P&L and mutually exclusive holding-time cohorts.

| Observed completed-trade category | v0.1 trades | v0.1 net P&L | v0.2 trades | v0.2 net P&L |
|---|---:|---:|---:|---:|
| Held 6 hours or less | 11 (0 positive, 11 negative) | -$3.174604 | 11 (0 positive, 11 negative) | -$3.021619 |
| Held >6 hours and <24 hours | 10 (0 positive, 10 negative) | -$2.585837 | 9 (0 positive, 9 negative) | -$2.748671 |
| Held 24 hours or more | 12 (7 positive, 5 negative) | +$0.952802 | 11 (7 positive, 4 negative) | +$0.868014 |
| **Completed-trade total** | **33 (7 positive, 26 negative)** | **-$4.807639** | **31 (7 positive, 24 negative)** | **-$4.902276** |
| Remaining open-position mark | 1 | -$0.105257 | None | $0 |

The 24-hour cutoff was observed **after trades closed**. It is an outcome label, not information known at entry. These descriptive observations **do not** justify an artificial minimum holding period: a forced delay can increase losses or violate risk controls. Duration buckets from two highly related strategies on the same sample are not independent confirmations.

The next distinct program, `PYTHONPATH=src python -m signal_vault.research_entry_context`, makes NO trading rule changes and reads only this same pre-gap development file. It reports median entry-time EMA spread, prior 6-hour and 24-hour return, 24-hour range, and signed trend efficiency for *subsequently* winning/loss-making and short-/long-duration completed trades. Every entry feature uses strictly the **closed candles preceding the hypothetical BUY execution candle**, never the candle's future OHLCV or eventual outcome. Results are exploratory small-sample observations, not optimized thresholds, causal evidence, or authorization to trade.

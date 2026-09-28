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

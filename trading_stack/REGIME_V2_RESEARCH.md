# $500 multi-strategy checkpoint — October 4, 2026

Status: implemented and tested research candidate; rejected for promotion.
No new paper worker started, no live trading enabled, no prospective results.
The dashboard and original campaign configuration are unchanged.

## What changed

An opt-in `regime-v2` pack adds distinct closed-hour breakout, trend pullback,
and range-reversion entries. EMA/ADX determine market regime, RSI times recovery,
volume confirms breakouts, and ATR sets stop/target distances. Long inverse-ETF
pullbacks remain paper-only and subject to the existing session exits. Crypto
remains internal spot simulation. Stocks and Kalshi require their existing
credentials; Kalshi additionally requires independent calibrated probability
evidence. These indicators are rules, not forecasts or proof of an edge.

The candidate uses one shared $500 virtual account, 0.5% budgeted risk per trade,
2% daily loss trigger, 10% drawdown trigger, 20% maximum position allocation,
and 80% total entry allocation. Stops and risk triggers cannot guarantee loss
limits during gaps, downtime or thin liquidity. Fees and spread reserves count
toward sizing. Range targets stay at the actual prior mean; a refreshed entry
price must still clear modeled round-trip costs plus a 1% price-move buffer.
Other targets use three stop distances; costs cannot inflate that target just
to manufacture a qualifying opportunity. A valid no-trade decision remains.

The original `campaign.json` is preserved. The new
`campaign.regime-v2.json` is a research configuration, not a recommended worker
configuration. Do not deploy or allocate live capital to this rejected pack.
The worker's `SV_CONFIG` support already exists; no new execution activation
was added. Existing accounts reject changed configuration/source hashes rather
than silently resetting. An old account must keep its original source revision;
this candidate requires a separate campaign directory if a future explicitly
labeled experimental trial is chosen. No old state was accessed or modified.

## Actual historical result

Both packs used the same reduced risk policy and 0.8% per-side taker fee,
0.15% half-spread and 0.1% slippage per side. Tier 1 is a conservative fixed
fee scenario; volume-tier discounts and maker fills were not assumed.
Source: https://support.kraken.com/articles/cross-platform-fee-tier-changes.

| Already-inspected partition | Existing rules, costs corrected | New regime pack | New closed trades |
|---|---:|---:|---:|
| Development | -9.73% | -10.02% | 38 |
| Validation | -10.04% | -10.09% | 44 |
| Reused test, not a holdout | -10.53% | -10.53% | 43 |

All six accounts hit their drawdown halt. The new pack's profit factors were
0.075, 0.175 and 0.110. All three entry families had negative realized net P&L
in the partitions where they traded. This pack did not improve performance.
The prudent capital decision is not to promote either pack to live execution.

Each partition starts with an isolated $500 historical account; returns must
not be compounded together or called prospective performance. Fifteen configured
crypto assets were present in the user's Q1/Q2 archive. These data have already
influenced project research; no partition is an untouched holdout. No thresholds
were tuned after this comparison. Two predeclared packs were compared, not a
parameter tournament. The complete result includes source archive/per-asset
hashes, configuration/source hashes, costs, trades, blockers and attribution.
The inherited replay assumes next-hour entries, adverse same-hour stop ordering,
lagged volume caps and hourly risk checks. Actual fills, historical depth and
eligibility were not established. No operating costs, stock or Kalshi returns
are inferred. A stop's gap can overshoot the drawdown trigger.

## Validation and reproduction

49 tests passed: 40 existing execution/accounting tests plus nine new tests
covering three independent entry paths, Wilder indicator reference values,
closed-bar causality, invalid/gapped history, family selection, source freezing,
anchored targets, cost-aware rejection, shared sizing and duplicate prevention.
Fixture trades are isolated temporary accounts, never performance evidence.

```sh
python -m unittest trading_stack.test_cloud_paper trading_stack.test_regime_v2 -q
python -m trading_stack.cloud_paper.compare_regime \
  --archive /path/to/signal-vault-research.zip \
  --output trading_stack/research/regime-comparison-20261004.json
```

## Deployment and next decision

No cloud deployment was attempted. The existing hourly research collector was
preserved. A read-only Railway allowance inspection again returned “Agent usage
limit reached”; this is an inspection limit, not proof of exhausted hosting
credit. No no-charge continuous worker allowance was verified. Existing missing
Alpaca paper/Kalshi demo secrets and Kalshi model evidence remain unresolved.

Next: investigate whether a different executable venue/cost structure and
longer-horizon hypothesis can show positive after-cost results on genuinely
new data. Record every candidate, including failures. Do not tune the reused
archive until a pretty result appears or increase capital to hide a losing
percentage return. Deposit increases are separate cash flows, not profit.
Further strategy selection needs evidence; none was demonstrated in this run.

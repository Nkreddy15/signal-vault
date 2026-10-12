# Signal Vault: bounded paper exits

The native 15-minute campaign filled four crypto buys but retained swing exit rules: roughly 12% targets, trailing activation near 6%, and a 336-hour holding limit. All four positions occupied the account's four slots overnight. No sell order was attempted because none of those conditions fired. The worker remained healthy.

This release corrects the autonomous paper exit lifecycle. It is an experimental execution correction, with no demonstrated profitable edge. It keeps the requested 15-minute signal interval and scans every 30 seconds.

## Behavior

- Crypto positions exit at the next fresh executable quote after four hours, or after two completed post-entry 15-minute candles confirm a broken long trend. Range entries do not use the long-trend exit.
- A profit exit requires 0.3% of entry notional in net profit after modeled entry and exit fees and exit slippage. The actual bid threshold is shown in the position inspector alongside the original bracket. Small gross gains are not reported as net profits.
- Existing stops, original brackets, entries, fills, account identity, cash, fee history, realized/unrealized losses and campaign deadline are preserved. Overdue owned positions can close at current simulated quotes; historical fills are never invented.
- Same-pair re-entry waits at least two 15-minute bars after an actual exit and still requires a fresh autonomous strategy signal. No manual entry/close command is used.
- Modeled costs stay at 0.8% per side and 0.1% slippage per side; risk stays 0.5% per trade, four positions, 60% maximum exposure, 2% daily loss and 10% drawdown guards.
- PredictArb remains read-only. A Gamma markets HTTP 422 at a nonzero pagination offset resets the cursor for the next scan; coverage remains unavailable until a request succeeds. It does not create trades or alter cash.

## Negative historical evidence

The fixed comparison used overlapping native 15-minute public history from October 5, 16:15 UTC through October 12, 13:30 UTC. These were independent $500 retrospective scenarios, using identical entries, sizing, risk and costs. Parameters were declared before this comparison; no search or winning variant selection was performed.

| Exit policy | Closed trades | Final equity | Net return | Modeled fees |
|---|---:|---:|---:|---:|
| Prior long hold | 5 | $486.47 | -2.71% | $5.40 |
| Bounded paper exits | 42 | $456.50 | -8.70% | $31.45 |

Shorter exits generated more completed cycles and substantially greater fee-driven losses. These results do not support profitability, real-money activation, or an increase in risk. The paper experiment continues to collect autonomous execution evidence with truthful P&L; faster trading is not a profitability claim. This short overlapping replay is not an untouched holdout or a prospective result.

Evidence is in `bounded_exit_comparison_20261012.json` and `native15m-exits-20261012.json.gz`. Run `python -m trading_stack.research.replay_exits_20261012` to reproduce the fixed comparison.

An isolated copy of the live account also closed the exact four owned quantities, retaining the campaign ID/deadline and prior fee history. It realized a modeled $5.58 loss at its test quotes. `bounded_exit_copied_runtime_20261012.json` is explicitly a copied-account test, not a cloud result.

## Validation and rollout

- 132 Python tests passed, covering exact owned quantities, overdue exits, positive and negative net fee accounting, stale/partial/gapped candles, stale quotes, insufficient depth, cooldown, idempotent revision/restart and refusal of changes to entries/costs/risk or accounts with pending orders.
- Both accepted-dashboard DOM/API harnesses passed. CSS, the template and `dashboard.js` remain untouched; only functional inspector fields in `cloud.js` changed. No visual browser verification is claimed.
- Supervisor takes the worker lock, creates an integrity-checked backup and requires the exact prior configuration hash `96456cacb3b6cd068a1f7d2c85802879bea45a177f71a58998db538208bcc2aa` before the one-time exit revision. `SV_ALLOW_NEW_CAMPAIGN=0` remains set. After confirmation, clear the one-time revision variable without redeploying.
- New config: `trading_stack/cloud_paper/campaign.intraday-exits.json`. Crypto stays internal simulation on Kraken public data; stocks/Kalshi remain credential-blocked, DEX/PredictArb read-only, and paid AI calls disabled.
- Railway's existing free-plan sleep setting remains a limit on guaranteed unattended availability.

Before rollout at 14:11 UTC the actual cloud account had four open positions, zero closes, equity $495.66 and modeled net P&L -$4.34. Deployment and actual fills must be checked separately after rollout; the historical and copied-account results above never count toward cloud P&L.

Kraken's current cross-platform lowest-volume taker rate was verified against https://www.kraken.com/features/fee-schedule and https://support.kraken.com/articles/cross-platform-fee-tier-changes . This is a conservative modeled allowance, not verification of an actual account's execution venue or tier.

## Verified actual cloud result

Railway deployment `54066c0c-5824-4273-aa7b-dc534bde2bce` succeeded with runtime commit `d3ed10dc30fa3eb2dfc26c4aa7db9c8e8ea7c5ed`. At 14:24:43 UTC, the unchanged account had four closed positions, no open positions, cash/equity $494.5677009214, realized/net P&L -$5.4322990786, and $3.1128907901 in total modeled paid fees. All four sells were filled for the exact prior owned quantities and had `INTRADAY_TIME_EXIT` reasons. No owner close or flatten command was used; a concurrent resume control is retained in the ledger.

The account identity, start, October 18 deadline, original entry prices/brackets, prior fees and financial history all reconciled. SQLite integrity was `ok`; no pending orders remained. Health, authenticated candles/opportunities/static assets returned 200, while an unauthenticated snapshot returned 401. The paper worker was online with one replica; the separate collector cron remained successful and no services had recent failures. The one-time revision variable was cleared without another deploy.

`exit_cloud_proof_20261012.json` contains the redacted reconciliation. The source is pinned to the runtime commit; later documentation/evidence commits do not redeploy it. Crypto remains simulation, other trading lanes remain blocked/read-only, and no profitability is claimed.

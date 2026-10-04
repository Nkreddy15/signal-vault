# Signal Vault cloud paper checkpoint — 2026-10-04

## Delivery status

**Implementation checkpoint, not a running cloud deployment. No prospective performance results exist for this campaign.**

Source base: `phase-162-multimarket-reset` at `0ea16f645ac340dcc8c7b1f192ef3c98eb8e1bd7`.
Review branch: `cloud-paper-multimarket-20261004`; draft PR https://github.com/Nkreddy15/signal-vault/pull/186. Initial remote checkpoint: `ab9b51495dea57a9fa986b04961a072b2f394d5d`; later commits on the same PR contain the additional evidence below.

The existing V11 code, account files, research and dashboard assets are preserved. This adds an isolated, new $500 total virtual portfolio; it does not migrate or reset the old V11 account. No real-money trading is implemented or enabled.

## Implemented

- `cloud_paper/`: one SQLite financial writer, WAL/full synchronization, frozen configuration and deadline, durable controls and order intentions, cumulative partial-fill accounting, restart reconciliation, shared reservations and exposure limits, provider health and SQLite backups.
- Crypto: the existing 15-asset universe, Kraken public data, venue minimums and depth checks, explicitly internal simulation. No exchange order submission.
- Stocks: fixed Alpaca paper host, account/calendar/core-session checks, fractional DAY limit orders, buying power, client-ID recovery and position reconciliation. Bearish exposure uses long SH/PSQ with a session/time limit, not unsupported fractional shorting.
- Kalshi: fixed demo execution host, signed requests, bounded public/demo discovery, binary YES contract order books, IOC order intentions, positions and exchange settlement receipt reconciliation. Execution receipts provide YES-scale buy costs and sell proceeds, actual fees and execution timestamps; order/fill quantity or fee disagreement blocks reconciliation. Only a freshly verified standard quadratic fee schedule is accepted; event fee overrides and pagination are blocked for review. Independent timestamped probability and calibration evidence are mandatory for entries.
- Experimental closed-hour trend, breakout and range-reversion rules; deterministic conflicts and no forced trades. History initializes indicators on the first cycle; historical fills are never added to a prospective ledger.
- Existing dashboard template and original CSS/JavaScript retained. Conditional cloud additions connect total portfolio, all-market trades, order evidence, chart timeframes, equity curve, authenticated export and durable pause/resume/close/emergency controls. Pause leaves exits active; emergency pauses permanently and attempts to flatten owned paper positions when fresh data and the venue permit.
- Private Basic authentication, CSRF checks, security headers, heartbeat health endpoint, lightweight Docker definition and Railway configuration. Production startup refuses an ephemeral state directory.

## Verified locally

Command from repository root:

```sh
python -m unittest trading_stack.test_cloud_paper trading_stack.test_v11 trading_stack.test_v11_launcher trading_stack.test_v11_cloud -q
node trading_stack/test_final_dashboard.cjs
PYTHON=python node trading_stack/test_cloud_dashboard.cjs
```

2026-10-04: **74 Python tests passed** (40 new and 34 existing); **both dashboard DOM/API harnesses passed**. Tests cover isolated synthetic lifecycles/accounting, partial fills, duplicate and unknown submission handling, restart/config/deadline preservation, risk controls, stale prices, broker adapter payloads/signatures, exact receipts, settlement, backup rotation, historical adverse-fill ordering and authenticated endpoints. The cloud DOM harness exercises real API snapshot rendering, all-market trade selection, order evidence, on-chart versus off-chart fill markers, contract quote lines and authenticated control request construction. These are fixture results, not broker-confirmed executions or observed investment returns.

The loopback `qa_cloud_dashboard.py` uses a separate temporary fixture ledger. Its fabricated trades must never be reported as campaign results. Cloud Browser could not open loopback (`ERR_BLOCKED_BY_CLIENT`); desktop/mobile screenshot and real browser interaction verification remain outstanding. The Docker image has not been built in this environment. Docker is unavailable and a local Gunicorn install failed (`No matching distribution found` through this environment's package access); the production supervisor has not been exercised end to end here.

## Historical results (completed screening; no edge demonstrated)

The reproducible report is `research/cloud-paper-screening-20261004.json`; it includes archive/per-asset hashes, configuration/hash, assumptions, trade records, daily equity, costs, strategy attribution and descriptive uncertainty. The 15 configured crypto assets were screened from the supplied Q1/Q2 2026 archive. No parameters were tuned using this run. All data was already inspected in earlier project research; the 60/20/20 chronological partitions are **reused data, not untouched holdouts**.

| Reused partition (UTC) | Net return | Max drawdown | Closed trades | Profit factor | BTC after-cost baseline |
| --- | ---: | ---: | ---: | ---: | ---: |
| Jan 1–Apr 19 13:00 | −7.86% | 10.21% | 37 | 0.31 | −14.69% |
| Apr 19 13:00–May 25 17:00 | −10.28% | 10.28% | 38 | 0.14 | +1.38% |
| May 25 17:00–Jun 30 22:00 | −10.33% | 10.33% | 30 | 0.34 | −25.59% |

Cash returned 0% in each partition. All partitions hit the drawdown halt. Each starts with an isolated $500; horizon is extended to the partition length for this historical screen. Entry uses the next hourly open and prior closed-bar signals; incomplete hours are discarded. Costs are 0.4% fees, 0.15% half-spread and 0.1% slippage **per side**. Quantity is capped at 1% of the prior hour's volume. Stops precede targets on ambiguous bars, gaps receive the worse opening stop price, and trailing stops update for the next bar. Loss checks are hourly here, unlike the prospective 30-second worker. Historical spreads, depth, eligibility and lot rules are unavailable. Therefore the replay is an assumption-dependent screening model, not a claim that these fills were executable. Descriptive bootstrap intervals do not account for dependence or reused-data selection. No stock or Kalshi return is inferred. The proposed prospective campaign remains experimental.

Reproduce with the original user archive (not copied into Git):

```sh
python -m trading_stack.cloud_paper.research --archive /path/to/signal-vault-research.zip --output trading_stack/research/cloud-paper-screening-20261004.json
```

## Actual hosting state and blockers

- Railway access was verified: project `signal-vault-forward-research` (`11cfaecd-9956-46a7-b94a-99a1dc4cd4c9`), production environment `628e903d-c28f-42c1-bf59-9f7d91574dd0`.
- Existing service `btcusd-hourly-get-cron` (`d3d04ec9-1f74-428a-a4a3-03a35bce2dd2`) is an hourly research collector. Its logs explicitly disable orders. It has a 500 MB persistent volume at `/var/lib/signal-vault/forward`. It has not been repurposed or stopped.
- Rechecked at delivery: source remains `main`, schedule `7 * * * *`, latest successful deployment `6111a2a0-c48b-4833-8d22-d4158ddf9e61`, no domains or staged changes. Latest inspected runtime log is 2026-10-04 11:08:31 UTC (7:08 a.m. New York). That is collector activity, not new campaign trading.
- The other existing service has no source, deployment or volume. There is no deployed private dashboard URL for this new application.
- Account billing/free allowance could not be verified: the Railway agent returned “Agent usage limit reached.” That is a connector/agent limit, **not proof that hosting credits are exhausted**. No spend limit, plan, service or paid resource was changed.
- Official Railway pricing checked on 2026-10-04: Free includes $1/month usage credit; Hobby is $5/month including $5 usage, with excess billed. Storage and continuous worker usage count toward usage. A continuously running application is not verified to fit the user's free allowance. See https://docs.railway.com/pricing/plans.
- Missing execution secrets: `ALPACA_PAPER_KEY_ID`, `ALPACA_PAPER_SECRET`, `KALSHI_DEMO_KEY_ID`, `KALSHI_DEMO_PRIVATE_KEY_PEM`. Existing forward-research data credentials were not reused for trading.
- No defensible Kalshi probability/calibration dataset has been supplied or evaluated, so prediction entries remain blocked even if credentials are configured.
- A direct Kraken request did not return JSON earlier and timed out on the final connectivity check in this restricted execution environment. No fresh provider cycle has been verified on a deployed worker.

## Work still required before calling this deployment-ready

1. Confirm adapters against current connected Alpaca paper and Kalshi demo responses, including buy/sell/partial-fill/cancel/settlement receipts. The current verification is fixture-based. Alpaca cumulative partial-fill observation timestamps are labeled when exact execution time is unavailable; they are not claimed to be per-fill broker timestamps.
2. Exercise supervisor restart and Docker startup in a network-capable build environment, and finish browser interaction/desktop/mobile QA. Existing visual design is preserved, but responsive screenshots have not been verified.
3. Reserve new future data for the prospective record. Completed reused historical screening is negative; no tested edge is asserted.
4. Verify remaining no-charge hosting credit, hard spending protection and a durable volume placement that preserves the research collector. If no verified free option fits, request explicit cost approval before creating paid resources.
5. Configure secrets directly in hosting settings, build the image, deploy one worker, verify HTTPS/auth, persistent restart, current data and an isolated controlled lifecycle. Only then initialize the real new $500 experimental paper campaign and report its actual start/deadline.

## Deployment configuration (prepared, not executed)

Build from repo root with `trading_stack/Dockerfile.cloud-paper`; select `trading_stack/railway.cloud-paper.toml` as the service config file. Use one replica, no sleep or cron schedule, and a mounted persistent volume. Keep the old collector's directory separate.

```text
SIGNAL_VAULT_MODE=paper
SV_STATE_DIR=/data/cloud-paper
SV_ALLOW_NEW_CAMPAIGN=1
SV_DASHBOARD_USER=nikhil
SV_DASHBOARD_PASSWORD=<unique random value of at least 32 characters>
ALPACA_PAPER_KEY_ID=<paper account key>
ALPACA_PAPER_SECRET=<paper account secret>
KALSHI_DEMO_KEY_ID=<demo key ID>
KALSHI_DEMO_PRIVATE_KEY_PEM=<demo private key>
```

Use the provider-injected `PORT` and persistent mount environment. `SV_LOCAL_TEST=1` is only for an isolated local test, never cloud production. Keep credentials out of Git and chat. Hourly snapshots rotate only this new campaign's own backups: at most eight regular snapshots, with an approximately 120 MiB previous-snapshot budget retaining the two newest. The ledger, fills, research and old V11 state are never pruned. Backups refuse insufficient space; new entries stop below 32 MiB free space while exits continue. Backup errors are exposed on the dashboard. Snapshots remain on the same volume; authenticated SQLite export is available, but offsite backup/restore has not been verified. Resume the same state directory/configuration; never delete the database to restart a campaign.

Deployment smoke gates: authenticated snapshot and unauthenticated 401; fresh worker heartbeat and provider data; isolated controlled buy/partial/cancel/sell accounting; kill/restart with unchanged account/config/deadline and no repeated POST; persistent volume checksum/integrity and backup restoration; desktop/mobile trade inspector and chart/control interaction. Keep fixture ledgers in a different directory from the real campaign. Only after these pass should `SV_ALLOW_NEW_CAMPAIGN=1` initialize the new campaign, then remove that flag from the service to guard against accidental replacement of missing state. A 168-hour run starts at actual initialization; it has not started here.

Official adapter references checked during implementation: https://docs.kalshi.com/api-reference/orders/create-order-v2, https://docs.kalshi.com/api-reference/portfolio/get-fills, https://docs.kalshi.com/api-reference/market/get-series, https://docs.kalshi.com/api-reference/events/get-event-fee-changes, https://docs.kalshi.com/getting_started/demo_env, https://docs.alpaca.markets/docs/fractional-trading and https://docs.alpaca.markets/docs/paper-trading.

The immediate next engineering action is to resolve the explicitly listed deployment-readiness checks. The immediate access action is to verify Railway's actual allowance/spending protection, without enabling charges.

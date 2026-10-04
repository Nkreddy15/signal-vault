# Signal Vault cloud paper checkpoint — 2026-10-04

## Delivery status

**Implementation checkpoint, not a running cloud deployment. No prospective performance results exist for this campaign.**

Source base: `phase-162-multimarket-reset` at `0ea16f645ac340dcc8c7b1f192ef3c98eb8e1bd7`.
Review branch: `cloud-paper-multimarket-20261004`.

The existing V11 code, account files, research and dashboard assets are preserved. This adds an isolated, new $500 total virtual portfolio; it does not migrate or reset the old V11 account. No real-money trading is implemented or enabled.

## Implemented

- `cloud_paper/`: one SQLite financial writer, WAL/full synchronization, frozen configuration and deadline, durable controls and order intentions, cumulative partial-fill accounting, restart reconciliation, shared reservations and exposure limits, provider health and SQLite backups.
- Crypto: the existing 15-asset universe, Kraken public data, venue minimums and depth checks, explicitly internal simulation. No exchange order submission.
- Stocks: fixed Alpaca paper host, account/calendar/core-session checks, fractional DAY limit orders, buying power, client-ID recovery and position reconciliation. Bearish exposure uses long SH/PSQ with a session/time limit, not unsupported fractional shorting.
- Kalshi: fixed demo execution host, signed requests, bounded public/demo discovery, binary YES contract order books, IOC order intentions, positions and exchange settlement receipt reconciliation. Independent timestamped probability and calibration evidence are mandatory for entries.
- Experimental closed-hour trend, breakout and range-reversion rules; deterministic conflicts and no forced trades. History initializes indicators on the first cycle; historical fills are never added to a prospective ledger.
- Existing dashboard template and original CSS/JavaScript retained. Conditional cloud additions connect total portfolio, all-market trades, order evidence, chart timeframes, equity curve, authenticated export and durable pause/resume/close/emergency controls. Pause leaves exits active; emergency pauses permanently and attempts to flatten owned paper positions when fresh data and the venue permit.
- Private Basic authentication, CSRF checks, security headers, heartbeat health endpoint, lightweight Docker definition and Railway configuration. Production startup refuses an ephemeral state directory.

## Verified locally

Command from repository root:

```sh
python -m unittest trading_stack.test_cloud_paper trading_stack.test_v11 trading_stack.test_v11_launcher trading_stack.test_v11_cloud -q
node trading_stack/test_final_dashboard.cjs
```

2026-10-04: **66 Python tests passed** (32 new and 34 existing); existing dashboard DOM harness passed. Tests cover isolated synthetic lifecycles/accounting, partial fills, duplicate and unknown submission handling, restart/config/deadline preservation, risk controls, stale prices, broker adapter payloads/signatures and authenticated endpoints. These are fixture results, not broker-confirmed executions, new historical strategy validation or observed investment returns.

The loopback `qa_cloud_dashboard.py` uses a separate temporary fixture ledger. Its fabricated trades must never be reported as campaign results. Cloud Browser could not open loopback (`ERR_BLOCKED_BY_CLIENT`); desktop/mobile screenshot and real browser interaction verification remain outstanding. The Docker image has not been built in this environment.

## Actual hosting state and blockers

- Railway access was verified: project `signal-vault-forward-research` (`11cfaecd-9956-46a7-b94a-99a1dc4cd4c9`), production environment `628e903d-c28f-42c1-bf59-9f7d91574dd0`.
- Existing service `btcusd-hourly-get-cron` (`d3d04ec9-1f74-428a-a4a3-03a35bce2dd2`) is an hourly research collector. Its logs explicitly disable orders. It has a 500 MB persistent volume at `/var/lib/signal-vault/forward`. It has not been repurposed or stopped.
- The other existing service has no source, deployment or volume. There is no deployed private dashboard URL for this new application.
- Account billing/free allowance could not be verified: the Railway agent returned “Agent usage limit reached.” That is a connector/agent limit, **not proof that hosting credits are exhausted**. No spend limit, plan, service or paid resource was changed.
- Official Railway pricing checked on 2026-10-04: Free includes $1/month usage credit; Hobby is $5/month including $5 usage, with excess billed. Storage and continuous worker usage count toward usage. A continuously running application is not verified to fit the user's free allowance. See https://docs.railway.com/pricing/plans.
- Missing execution secrets: `ALPACA_PAPER_KEY_ID`, `ALPACA_PAPER_SECRET`, `KALSHI_DEMO_KEY_ID`, `KALSHI_DEMO_PRIVATE_KEY_PEM`. Existing forward-research data credentials were not reused for trading.
- No defensible Kalshi probability/calibration dataset has been supplied or evaluated, so prediction entries remain blocked even if credentials are configured.
- A direct Kraken request did not return JSON in this restricted execution environment. No fresh provider cycle has been verified on a deployed worker.

## Work still required before calling this deployment-ready

1. Complete review of Kalshi execution-price/fee receipts and enforce supported fee schedules. Confirm buy and sell accounting against current demo responses.
2. Bound backup storage, exercise supervisor restart and Docker startup, and finish browser interaction/desktop/mobile QA.
3. Run the new frozen strategy rules on the available historical archive with costs and chronological reporting. Existing data has already influenced earlier research; it cannot honestly be called an untouched test set. Reserve new future data for the prospective record.
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

Use the provider-injected `PORT` and persistent mount environment. `SV_LOCAL_TEST=1` is only for an isolated local test, never cloud production. Keep credentials out of Git and chat. Backups currently reside on the same volume; authenticated SQLite export is available, but offsite backup/restore has not been verified. Resume the same state directory/configuration; never delete the database to restart a campaign.

The immediate next engineering action is to resolve the explicitly listed deployment-readiness checks. The immediate access action is to verify Railway's actual allowance/spending protection, without enabling charges.

# SIGNAL VAULT — durable checkpoint

**Checkpoint:** PHASE2-2026-09-28-G (local operator dashboard, PAPER safety preflight, owner-only backups and risk-policy hardening).
**Repository:** private https://github.com/Nkreddy15/signal-vault, `main`. Phase 2F was verified remotely; latest Phase 2G source must be compared against remote tree and exact-tree synced before ending this session. No force push.
**Authorization:** Development and offline/PAPER-only architecture. No deposits, paid services, broker credentials, authenticated provider API calls, real paper orders, real-money trades or deployment. Live trading endpoint is absent.
**Target:** November 1, 2026 conditional $100 live pilot only after actual provider paper validation, risk gate and new explicit live authorization. Deadline does not override release criteria or imply profitability.

## Verified completed

- All prior Phase 1/Phase 2F code retained: versioned research pipeline, BTC/USD EMA baseline, deterministic Guardian, logical $100 ledger, authenticated-read client boundaries (not activated), paper order state, exactly-once draft submission attempts, no-blind-retry UNKNOWN_RESULT recovery, fee/order/position audit (fake-transport tests), single-runtime file lock, operator halt, local health and alert sinks and unattended paper-only daemon shell.
- Phase 2G `operator_view.py` and `operator_server.py`: read-only snapshot from existing SQLite, HTTP Basic-token authentication (32+ random chars), **127.0.0.1 only**, JSON `/api/status` and small auto-refreshing private HTML owner view. No broker calls, orders, raw event/provider payloads, secrets, or dashboard control POST; report labels explicit that balances are local paper journal, not live market value.
- `preflight.py` validates an existing PAPER DB owner/mode, disk headroom, SQLite quick_check, reconciled logical snapshot; unresolved orders flag same-order-id lookup rather than granting submission. Never opens provider API.
- `init_paper.py` allows explicit offline $100 local journal bootstrap without keys; SQLite file is created/tightened to owner-only mode 0600 before open, and sidecar WAL/SHM tested owner-only.
- `local_backup.py` creates online consistent SQLite snapshots in private directory with exclusive atomic publication, integrity check and SHA-256; never overwrites an old backup or authorizes resumed trading from restored state. Includes Symlink/disk-pressure tests.
- `ops/systemd` contains **uninstalled** example single-host paper service and localhost monitor; documented deployment safeguards, security and explicit host authorization gate.
- Guardian `RiskLimits` now rejects non-finite, zero, negative, inconsistent, malformed policy values; risk engine rejects malformed IDs, timestamps, position maps, unexpected symbols, invalid halt state and inconsistent marked equity. A previous synthetic reconciliation test fixture now correctly derives its portfolio from the logical ledger.
- Offline test evidence: `make test` **162/162 PASS**, `make compile` PASS; offline demo remains `DRY_RUN_RECORDED_NOT_FILLED`. All provider interactions in tests use fake transports.

## Limitations — never report these as completed

- No authenticated Alpaca paper credentials/smoke, genuine historical BTC/USD provider dataset, genuine paper POST, provider-confirmed fill or seven-day monitored account run.
- No PostgreSQL critical transaction ledger; SQLite remains a **single-host prototype**. Do not describe backup + file lock as distributed HA.
- Dashboard is a local ledger monitor, not public SaaS hosting and not a current NAV/quote/performance service. `systemd` files are examples and are not installed/deployed.
- No external Telegram delivery, no stocks, Kalshi, real-money adapter or user-approved cloud spend. The versioned EMA strategy is not evidence of positive after-cost alpha.
- A restore of an old backup requires an independent provider reconciliation before any new paper order. No automatic restore/run command exists.

## Resume protocol

Read latest GitHub `main` files `PROJECT_STATUS.md`, `NEXT_STEPS.md`, `ARCHITECTURE.md`, `docs/OPERATOR_MONITOR.md` and `docs/DEPLOYMENT_PREPARATION.md`. Verify remote head and tree, run `make test`, `make compile` and `make demo`, then continue PAPER-only work. Never overwrite newer remote changes with stale local archives, and never enable live execution. Commit exact-tree verified checkpoints at session end; no autonomous development continues between user turns.

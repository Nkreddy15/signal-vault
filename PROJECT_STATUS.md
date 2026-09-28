# SIGNAL VAULT — durable checkpoint

**Checkpoint:** PHASE2-2026-09-28-F (unattended paper-runtime hardening; provider credentials/order submission NOT activated).
**Repository:** private https://github.com/Nkreddy15/signal-vault, branch `main`. Phase 2F code tree was exact-tree synced to private GitHub as commit `e56a741705d1d182bd22ab4c03628dd92ed9c2f3`, tree `b221891c52f27fd3381261787a0957bf549ba130`; this documentation-only follow-up records that successful handoff.
**Authorization:** Development and paper-mode architecture only. No deposits, paid services, broker credentials, authenticated broker requests, genuine paper orders, real-money orders, real-money account connections or deployment have occurred. There is no live-trading endpoint in the codebase.
**Target:** November 1, 2026 *conditional* $100 live pilot only after genuine provider paper validation and a separate explicit live authorization; profitability and launch are not promised.

## Verified completed

- All Phase 2E research, Guardian, authenticated fixed-host data readers, logical $100 accounting, paper order state, fill/fee audit, reconciliation, restart safety, provider-drift checks and one-cycle paper runtime remain intact.
- Durable operator halt/resume is now stored and audited in the local ledger. Recovery/reconciliation still runs while halted, but no new draft or POST can occur.
- UTC daily-loss session baseline now resets automatically on the first legitimate mark of a new UTC date instead of depending on a scheduler caller remembering to reset it.
- `runtime_lock.py` provides an owner-only nonblocking OS file lock (with symlink refusal where supported) so a daemon and one-cycle worker cannot intentionally operate the same SQLite journal concurrently.
- `paper_daemon.py` provides the unattended **paper-only** scheduler shell: deterministic cadence by runtime state, clean SIGTERM/SIGINT stop flag, shared single-instance lock, atomic health updates and local alert hooks. It inherits the exact paper-only POST acknowledgement gate and has no live host.
- Scheduler behavior avoids busy loops: active provider lifecycle is polled quickly, bad market data retries after a bounded delay, reconciliation/fee/provider-drift faults back off, normal HOLD waits until shortly after the next UTC hour close, and operator halt is rechecked each minute.
- Unexpected scheduler exceptions fail closed as `BLOCKED_RUNTIME_EXCEPTION`, write a health state without exception/provider body text, stop the daemon and require operator review.
- `health.py` writes atomic owner-only JSON containing only safe logical portfolio/runtime state; raw provider responses, provider account IDs and credentials are excluded.
- `alerts.py` writes owner-only local JSONL state-transition alerts without exception/provider payloads. No external notification service is connected or authorized.
- `control.py` is a local-only halt/resume/status CLI and imports no broker/network client.
- The one-cycle paper worker now participates in the same runtime lock as the daemon; a custom lock path can be supplied consistently through `SIGNAL_VAULT_RUNTIME_LOCK`.
- Local checks after Phase 2F changes: `make test` **136/136 PASS**, `make compile` PASS, `make demo` still prints `DRY_RUN_RECORDED_NOT_FILLED`.

## Limitations — never claim these are finished

- No Alpaca paper credentials have been supplied and no genuine authenticated API request or paper order has been made. All network-bound order lifecycle tests use fake transports.
- The unattended scheduler is code-complete enough for controlled paper integration tests but has not run continuously against a provider account.
- SQLite is intentionally single-writer and now process-locked, but it is not a high-availability database. PostgreSQL remains the persistence gate before cloud unattended paper operation unless a narrowly scoped single-host SQLite pilot is explicitly justified.
- No cloud/service-manager deployment, external notifications, private dashboard, seven-day genuine provider-paper run, stocks, Kalshi/event-contract execution or real-money connector.
- Current EMA strategy is a deterministic baseline candidate, not a demonstrated trading edge. Software reliability tests are not evidence of profitability.
- Provider metadata, rate limits, activity timing, fees, account eligibility and real response schemas must be checked with authenticated read-only smoke tests before any paper POST acknowledgement is enabled.

## Resume protocol

Use latest private GitHub `main` as source of truth after Phase 2F sync. Read `PROJECT_STATUS.md`, `NEXT_STEPS.md`, `ARCHITECTURE.md` and `docs/API_PROVIDER_ASSUMPTIONS.md`; verify remote head/tree; run `make test`, `make compile`, and `make demo`; then continue paper-only development. Never enable or add live execution. Create and verify an exact-tree GitHub checkpoint before stopping a session.

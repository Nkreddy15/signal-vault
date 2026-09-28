# SIGNAL VAULT — durable checkpoint

**Checkpoint:** PHASE1-2026-09-28-B (verified private GitHub main branch, full 24-file source-tree import).  
**Authorization:** Phase 1 architecture, repository scaffold and paper-only development ONLY. No deposits, paid services, broker account connections, market orders, real-money trades or deployments authorized.  
**Target:** November 1, 2026 *conditional* $100 live pilot; no promise of profitability or go-live.

## Completed in this checkpoint

- Created modular-monolith system design in `ARCHITECTURE.md`.
- Documented security, acceptance gates, ADRs, delivery schedule, a PostgreSQL design migration and CI workflow.
- Wrote Python offline safety kernel: venue-aware intent, portfolio snapshot, `Decimal` accounting inputs, deterministic Guardian checks, strict runtime lock, idempotent local dry-run broker.
- Created repeatable Python standard-library unit tests. Local verification: **24/24 unit tests passed**; offline demo printed `DRY_RUN_RECORDED_NOT_FILLED`; attempted live mode was rejected; source and tests compiled. Re-run tests in each future session.

## Not yet implemented — do not claim otherwise

- Private GitHub repository established at https://github.com/Nkreddy15/signal-vault. The remote Phase 1 source tree SHA `78f21d5eafbea9a70fc60fadcbbeae85a10cb099` exactly matches the original local Git tree. Remote initial full-source commit `efb4b0c786701a909c7b9c9e67f54c9392e08613`.
- No Alpaca credentials, SDK connection, API paper orders, trading data feed or historical strategy.
- No persistent live ledger, PostgreSQL instance, working dashboard, public URL, cloud deployment, scheduled autonomous loop or real fill/P&L.
- No stocks / Kalshi market integrations. No live-money execution path exists.

## GitHub source of truth

Private repository: https://github.com/Nkreddy15/signal-vault (branch `main`). Initial complete 24-file import: commit `efb4b0c786701a909c7b9c9e67f54c9392e08613`; verified tree SHA `78f21d5eafbea9a70fc60fadcbbeae85a10cb099`, exactly matching the original local source tree. The earlier local commit has a different SHA because the new remote was initialized separately, but its file tree is identical. GitHub is now the authoritative development source. Never overwrite GitHub files from an outdated archive without comparing state.

## Resume instructions

Read this file and `NEXT_STEPS.md` from the GitHub `main` branch. Inspect actual Git state before making claims. Preserve paper-only constraints and rerun all tests. Update this status file at each successful checkpoint. Never rely on chat memory alone.

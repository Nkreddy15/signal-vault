# SIGNAL VAULT — durable checkpoint

**Checkpoint:** PHASE1-2026-09-28-A (initial local Git commit).  
**Authorization:** Phase 1 architecture, repository scaffold and paper-only development ONLY. No deposits, paid services, broker account connections, market orders, real-money trades or deployments authorized.  
**Target:** November 1, 2026 *conditional* $100 live pilot; no promise of profitability or go-live.

## Completed in this checkpoint

- Created modular-monolith system design in `ARCHITECTURE.md`.
- Documented security, acceptance gates, ADRs, delivery schedule, a PostgreSQL design migration and CI workflow.
- Wrote Python offline safety kernel: venue-aware intent, portfolio snapshot, `Decimal` accounting inputs, deterministic Guardian checks, strict runtime lock, idempotent local dry-run broker.
- Created repeatable Python standard-library unit tests. Local verification: **24/24 unit tests passed**; offline demo printed `DRY_RUN_RECORDED_NOT_FILLED`; attempted live mode was rejected; source and tests compiled. Re-run tests in each future session.

## Not yet implemented — do not claim otherwise

- No new GitHub `signal-vault` remote (connected GitHub account does not have one; tool supports file writes but not repository creation).
- No Alpaca credentials, SDK connection, API paper orders, trading data feed or historical strategy.
- No persistent live ledger, PostgreSQL instance, working dashboard, public URL, cloud deployment, scheduled autonomous loop or real fill/P&L.
- No stocks / Kalshi market integrations. No live-money execution path exists.

## GitHub remote blocker

The linked GitHub account is `Nkreddy15`. Existing repositories do not contain Signal Vault. To avoid contaminating another project, the first checkpoint is initialized as a local Git repo and archived in the ChatGPT Library. The user must create a **new empty private** repository called `signal-vault` at https://github.com/new (do not initialize it with a template/README/license). Then provide its URL in the next turn to enable pushing this exact checkpoint through the connected tools or using standard local Git credentials.

## Resume instructions

Read this file and `NEXT_STEPS.md` from the saved Phase 1 archive / Library. Inspect actual Git state before making claims. Preserve paper-only constraints and rerun all tests. Update this status file at each successful checkpoint. Never rely on chat memory alone.

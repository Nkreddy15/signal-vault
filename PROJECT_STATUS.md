# SIGNAL VAULT — durable checkpoint

> **2026-09-28 Phase 2-C handoff:** Latest complete tested source is in the ChatGPT Library at `/Signal Vault/signal-vault-phase2C-2026-09-28.zip` (45 tracked files plus local Git history; local commit `e55680e612296be7c0c550defdcf68253b5121fa`; local full tree SHA `b9feceab2cbefdb998d642cdb22d81685cf51ed3`; archive SHA-256 `11a0063274e7b504762c8a8cdd952bda3306d5cf90cf82e9a96e14506f37a35a`). 74/74 local offline tests PASS. Phase 2-C includes validated BTC historical ingestion, EMA and cost-aware hypothetical backtesting, strict $100 paper-planning budget, a mock-tested GET-only paper reader, SQLite draft/actual-order state foundations, a single-attempt paper-only POST adapter (not invoked with real keys), uncertain-timeout recovery, and a local source-sync helper at `scripts/publish_private_checkpoint.sh`. **This GitHub branch currently retains Phase 1 CODE only.** Files backend returned HTTP 401 when transferring Phase 2 source. The optional source-sync script safely merges the newest ZIP with the private repo using regular Git push; do not force-push or assume Phase 2 is synced. No authenticated brokerage activity, provider paper orders, real-money operations, purchases or deployments occurred.

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

# SIGNAL VAULT — durable engineering checkpoint

**Checkpoint:** PHASE2-2026-09-28-I (combined PAPER-only research/operations work; private owner-read and control surfaces audited; 225 offline tests passed).
**Private repository:** https://github.com/Nkreddy15/signal-vault (`main`). Prior remote Phase 2H commit `338094301d368a7d5afe506ebcd47884bec330ed`, exact file tree `e17305a09eeda46465d825dd507eb8ca2e9c4347`. Phase 2I source must be separately exact-tree synced before stopping; do not force-push or overwrite others' work.
**Authorization/status update (owner-run, 2026-09-28):** Development and local/offline/PAPER-only implementation. The owner reports successful local authenticated Alpaca PAPER read-only account smoke and read-only BTC/USD quote/history capture. Keys were never supplied to ChatGPT or committed to GitHub. No broker paper POST, cash deposit, live order, live endpoint, cloud deployment, purchase or public publishing has occurred.
**Deadline:** November 1, 2026 is a *conditional* target for an owner-authorized $100 experiment, not a guaranteed profitable system or automatic live launch.

## Verified completed engineering work

- Modular single platform with market-adapter contracts; enabled candidate market is BTC/USD PAPER, not stocks/Kalshi. Deterministic closed-hour EMA crossover baseline, versioned evidence/HOLD; chronological research fold/backtester with hypothetical cost assumptions, research protocol and guarded promotion criteria. No verified alpha claimed.
- Market data strict validation, injectable READ-only provider adapters, authenticated read-only dataset-capture code with fingerprints (not called with real account), bounded read retry; stale/missing data fail closed.
- Deterministic Guardian for a logical $100 portfolio, example $15 single order/$30 combined exposure, $3 daily pause/$10 drawdown, no leverage; strong NaN/inconsistent-equity/invalid-policy checks. These are demo defaults, not an owner-approved live mandate.
- Durable local SQLite draft/idempotency/UNKNOWN_RESULT state, one unresolved order at a time, fill/fee/order/position audit, logical portfolio marks and cash, restart recovery and operator HALT. Fake-provider integration tests only; accepted provider order never mislabelled filled.
- Optional bounded LLM advisory code (`ai_advisory.py`) accepts an allowlisted public feature frame only; default paper worker/daemon does NOT load an AI transport. It may veto a new-money BUY but cannot place any order, override Guardian, alter limits, or veto the risk-reducing SELL path. Bad schema/transport fail closed.
- Separate optional logistic ML confirmation feature research, offline trainer, immutable JSON artifact and provenance/paper-shadow receipt gate. Model has not been trained on genuine broker data or promoted to live trading. Research modules and tests do not prove predictive ability.
- Paper-only one-cycle worker and unattended scheduling shell, owner-only single-process lock, bounded read retries, durable stop, classified safe local alerts, health report, source-labelled performance report and backup scheduling hooks. Never deployed.
- Local read-only HTML/JSON monitor `operator_server.py` defaults to 127.0.0.1:8766 with Basic token and cannot control orders. Separate Bearer-auth owner JSON control API defaults to 127.0.0.1:8765 with status/health/operator halt/resume ONLY. Status and resume now refuse a missing journal rather than silently creating a clean $100 account. These ports must never be exposed publicly.
- Local ledger preflight, private journal mode 0600, explicit init, consistent exclusive SQLite snapshot and integrity checks, optional daily local backups; restore never authorizes trading without provider reconciliation.
- systemd single-host paper/owner service **templates only** (including distinct monitor example). PostgreSQL isolated PAPER-only migration and transactional requirements are an **UNAPPLIED design**: no Python PG port, DB deployment or real PG tests yet.
- All tests executed locally: `make test` **225/225 PASS**, `make compile` PASS, `make demo` prints `DRY_RUN_RECORDED_NOT_FILLED`; test broker transports are fake. Live mode still hard fails. No genuine paper fills or claimed profit.

## Local empirical evidence and v0.2 development checkpoint (2026-09-28)

The owner reports four local BTC/USD hourly datasets, each with a matching independently checked SHA-256:
- Pre-gap 1,843 bars, 2025-12-25 22:00Z to 2026-03-12 17:00Z exclusive; `0f31fa3e6226a504db4b60185ae7388ae8979c14e3ccef1fc1b98e2b809071cc`.
- Confirmed missing source candle at 2026-03-12 17:00Z (the targeted Alpaca API GET also omitted it). The gap remains unfabricated.
- Post-gap older 2,476 bars, 2026-03-12 18:00Z to 2026-06-23 22:00Z exclusive; `56ce999182c0537b99ef9b7eff71ab9e6842e211ece7fcdfdff6c7dca90ca076`.
- 90-day research 2,160 bars; `131e6959c6e8f512238767fb3cb005de2cd3d378e9cefa8b774891d2773188bf`.
- Following seven-day 168 bars; `c6b96f1116f4a7ed7306a7b5ac2f2ce12225eaf8ad6d02a8327ad600689000b1`.

These CSVs and their manifests are retained locally on the owner's Mac, not checked into this source repository. The owner ran v0.1 on the 90-day research set (pre-holdout gate FAILED; final holdout negative), seven-day sample (negative) and pre-gap development set (67 simulated fills; -$4.9129 with modeled costs, -$1.4142 with zero costs; 7 of 33 completed trades profitable). v0.1 is not eligible for provider-paper shadow promotion. The previous 90-day final holdout is already examined, and must not be called unseen again.

New **v0.2 research-only candidate**, `docs/RESEARCH_V02.md`: unchanged 12/26 EMA and immediate SELL; an upward crossover BUY requires a second consecutive positive fully closed bar. Default v0.1 remains unchanged. `python -m signal_vault.research_v02` strictly permits only the verified pre-gap development dataset and reports v0.1 versus the candidate with and without modeled costs. **No actual candidate empirical result has yet been reported.** Current CI passed on Python 3.11 and 3.12 after adding v0.2 regression tests. Do not enable v0.2 in any paper worker/daemon or treat a better development fit as an edge.

## Still NOT completed / mandatory blockers

1. Alpaca PAPER account, local read-only smoke, BTC/USD quote and asset-rule checks have been reported successful by the owner; reconfirm broker/provider readiness and fee/quote behavior before any separately authorized paper POST. Preserve local secret storage; never send secrets through chat/GitHub.
2. Genuine historical BTC/USD data was captured locally (see above); v0.1 FAILED its fixed research gate. Complete predeclared offline v0.2 development, freeze before evaluating a reserved segment, acquire genuinely future holdout where possible, and separately review any ML paper-shadow proposal. No candidate is approved for real paper-order submission.
3. Complete transaction-integrity and restoration drills, an actual PostgreSQL Python port + PG concurrency tests or a separately reviewed single-host SQLite pilot acceptance. No multi-host execution against SQLite.
4. Separately authorized hosting, hardened service configuration and notifications. No services have been installed.
5. Actual broker PAPER execution with provider-confirmed order/fill/fee/cash/position reconciliation, at least seven days uninterrupted operation and incident review. Simulation result is not evidence of sustainable gains.
6. Live connector requires NEW owner decision, separate reviewed service/credentials, no withdrawal permissions and no automatic additional funding. No live code path exists.

## Resume procedure

Read GitHub `PROJECT_STATUS.md`, `NEXT_STEPS.md`, `ARCHITECTURE.md`, `docs/POSTGRES_PAPER_LEDGER.md`, `docs/OPERATOR_MONITOR.md`. Verify current remote head/tree, run `make test`, `make compile`, `make demo`; continue only PAPER development. All transactions and results must remain classified by real provider-paper vs offline synthetic vs genuine live (none). Create and verify a GitHub/Library exact-tree checkpoint before a session ends. Nothing runs in the background merely because the ChatGPT conversation is idle.

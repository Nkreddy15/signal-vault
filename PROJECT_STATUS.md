# SIGNAL VAULT — durable checkpoint

**Checkpoint:** PHASE2-2026-09-28-C (paper-only execution code under offline fake-transport tests).
**Repository:** private https://github.com/Nkreddy15/signal-vault, branch `main`. **IMPORTANT:** Remote currently contains Phase 1 source plus the disclosure notice, NOT the complete Phase 2 code, because the Library-to-GitHub source-transfer service returned HTTP 401. Latest tested Phase 2-C ZIP is saved separately in `/Signal Vault/` Library. Merge when transfer recovers; do not overwrite new remote changes.
**Authorization:** Development and offline/paper-mode only. No deposits, paid services, credential retrieval, authenticated broker calls, paper order submission, real-money orders, real-money account connections or deployment has occurred. Live order execution is NOT IMPLEMENTED.
**Target:** November 1, 2026 *conditional* $100 live pilot; no promise of profitability or launch.

## Verified completed

- Phase 1 modular architecture, deterministic Guardian, venue-aware intent and offline non-filling broker preserved.
- Private GitHub repository initialized, initial 24-file tree SHA `78f21d5eafbea9a70fc60fadcbbeae85a10cb099` exactly matched the original local tree. Phase 1 full-source GitHub commit `efb4b0c786701a909c7b9c9e67f54c9392e08613`.
- Phase 2 adds strict `market_data.py`: UTC hourly OHLCV validation; rejects incomplete, duplicate, gapped, impossible and future bars; public Alpaca crypto historical bars adapter with bounded pagination, read-only endpoint and injectable fake transport.
- Adds versioned `strategy.py`: deterministic 12/26 EMA-cross candidate signals; HOLD when no new crossover; evidence hash.
- Adds `backtest.py`: research-only $100 simulation; checks next-bar-open execution to avoid look-ahead, estimated costs, exposure and risk engine, unexecutable <$10 orders, unrealized open position marks and an explicit hypothetical-only report label. No observed trading advantage claimed.
- Adds `alpaca_paper.py`: allowlisted **GET-only** paper account/asset/order lookup boundary using immutable `https://paper-api.alpaca.markets`; no order submission, transfer, withdrawal or endpoint override; offline test mocks only. Non-executable BUY/SELL drafts enforce Guardian, GTC and estimated venue minimum. NO CREDENTIALS configured or used.
- Adds `journal.py`: durable SQLite local draft/idempotency/reservation/append-only audit foundation with an explicit $100 offline snapshot cap. This is NOT the genuine broker order/fill/reconciliation ledger; no broker orders are sent by this module.
- Revised *paper development* buy example to $15, open-plus-pending long exposure $30 because the documented Alpaca BTC/USD order minimum is ~ $10 and a $5 proposal would be unexecutable. Daily $3 and drawdown $10 illustrative safety pauses stay. These are **not** approved live authority limits.
- Added `paper_order_state.py`: conservative pure state machine with no HTTP; rejects duplicate submission, mismatch/regressing provider records, incomplete fills and unresolved broker terminal states. Unknown transport results require authoritative lookup, never blind retry.
- Added `offline_pipeline.py`: strict closed/fresh bar -> immutable signal -> HOLD or internally Guardian-checked *non-submitted* venue-sized draft -> atomic offline journal. Verified idempotency and stale-data rejection.
- Added fixed-parameter chronological research folds with non-overlapping evaluation windows and prior-only indicator warmup. These do NOT establish trading profitability.
- `paper_store.py` now makes the conservative paper order lifecycle persistent in SQLite, links an immutable Guardian-approved draft to the original client order ID, and reserves until explicit three-way provider reconciliation. One unresolved order blocks the next; a crash before a broker response cannot authorize a blind second POST.
- `paper_executor.py` contains a one-shot literal-paper-host-only POST adapter with no environment/live URL switch. It is NEVER invoked by the CLI; all integration tests use fake transports/credentials. Tests cover accepted vs filled, unknown timeout, malformed response, lookup recovery, paper status polling and no repeated POST after uncertainty.
- Restart recovery turns a pre-crash `SUBMISSION_PENDING` into `UNKNOWN_RESULT` and requires provider lookup; existing accepted/partial orders can be polled without another POST.
- Local checks: `make test` **74/74 PASS**, `make demo` prints `DRY_RUN_RECORDED_NOT_FILLED`; live-mode flag remains rejected. No connected broker paper fills.

## Limitations — never claim these are finished

- No verified/authenticated Alpaca paper account connection, no real historical market dataset collected, and no real-time quote feed.
- No authenticated paper order has actually been sent. Paper submission code is implemented but *inactive*; no broker-confirmed fill, genuine provider balance/fill reconciliation, production PostgreSQL instance, pending-sell base reservations or deployed worker.
- The research simulator is **hypothetical**, does not reproduce live/paper Alpaca matching or quote spreads, and is not evidence of profits.
- SQLite journal is an *offline draft journal*, not the production PostgreSQL ledger.
- No private dashboard, hosted deployment, notifications, 7-day provider paper run, stocks, Kalshi or real-money access.
- API sizes, support, rates and account eligibility must be checked against up-to-date provider metadata before actual paper orders.

## Resume protocol

Read `PROJECT_STATUS.md`, `NEXT_STEPS.md` and `ARCHITECTURE.md` from the latest GitHub `main` branch; compare SHA before writes, run `make test` and preserve paper-only restrictions. Do not overwrite newer remote changes with the older local ZIP. Update this file at every successful checkpoint. No autonomous work continues between ChatGPT sessions.

## Source-transfer contingency

Local Git commit history and a full project ZIP (including `.git`) reside in the Library snapshot `signal-vault-phase2C-2026-09-28.zip`. The GitHub main branch carries a visible note about the failed handoff and requires updating to the latest Phase 2-C state. The connector did not receive the Phase 2 source: the Files retrieval backend returned HTTP 401 on both `read` and `materialize`. Do NOT claim Phase 2 is on GitHub yet. Restore the full ZIP/manifest when authorized retrieval is available, or use a verified fast-forward/merge from a user local checkout.

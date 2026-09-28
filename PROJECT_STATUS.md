# SIGNAL VAULT — durable checkpoint

**Checkpoint:** PHASE2-2026-09-28-E (paper runtime/reconciliation/accounting foundation; all provider interaction still unverified with real credentials).
**Repository:** private https://github.com/Nkreddy15/signal-vault, branch `main`. Phase 2D is already verified on GitHub at tree `00f1bc3792006298fb3174d013601d15093a1732`; Phase 2E is the next exact-tree checkpoint to sync.
**Authorization:** Development plus paper-mode architecture only. No deposits, paid services, broker credentials, authenticated broker requests, genuine paper orders, real-money orders, real-money account connections or deployment have occurred in this work session. There is no live-trading endpoint in the codebase.
**Target:** November 1, 2026 *conditional* $100 live pilot after a genuine paper run and a new explicit live authorization; profitability and launch are not promised.

## Verified completed

- Phase 1 modular architecture, deterministic Guardian, venue-aware intents and offline non-filling broker preserved.
- Phase 2 research path: strict UTC hourly BTC/USD OHLCV validation, deterministic 12/26 EMA-cross candidate strategy with HOLD, evidence hashes, next-bar-open cost-aware hypothetical backtest and chronological non-overlapping evaluation folds. No backtest result is represented as broker performance.
- Paper-only account boundary in `alpaca_paper.py` is hard-bound to `https://paper-api.alpaca.markets`; GET allowlists cover account, BTC/USD asset metadata, positions, open orders, order lookup and order-filtered FILL/CFEE/FEE activities. No withdrawal, transfer or live-host route exists.
- `paper_credentials.py` accepts only explicit PAPER credential names and rejects generic/live key variables; secrets are redacted from repr/str.
- `venue_rules.py` parses provider-reported `min_order_size`, `min_trade_increment`, and `price_increment`; orders are rejected rather than silently upsized.
- `paper_order_state.py`, `paper_store.py`, `paper_executor.py`, and `paper_supervisor.py` implement persistent one-attempt paper-order lifecycle safety: durable pre-POST state, unique client IDs, UNKNOWN_RESULT after ambiguous failures, lookup-before-any-retry, no duplicate POST on restart, terminal state remains unreconciled until independent audit.
- `paper_audit.py` validates provider FILL identities, quantities and weighted fill price, and separately validates CFEE/FEE activities.
- `paper_reconciliation.py` independently verifies terminal order, FILL activities, active/unblocked paper account and BTC position. Logical accounting starts at exactly $100 and never adopts Alpaca's much larger default paper balance.
- Logical provider-fill accounting is atomic: buy/sell fills, cost basis, realized P&L, fee-equivalent reporting and reservation release are committed together. Unique provider order IDs cannot be applied twice.
- Crypto BUY fee timing is handled without trapping a position until end-of-day: if CFEE has not posted yet, net provider BTC inventory plus audited gross FILL quantity infers the exact BTC fee quantity, permits reconciliation/release, and queues a deferred fee audit. Later CFEE must match the inferred BTC quantity before its USD-equivalent valuation replaces the provisional amount. SELL USD fee remains a blocking reconciliation fact until provider FEE is available.
- `market_data.py` now has authenticated fixed-host historical BTC/USD bars and authenticated latest-quote readers. Latest quotes are rejected if stale/future, crossed or above the configured spread bound; BUY uses ask and SELL uses bid as the execution reference. The legacy unauthenticated historical default now fails closed because current provider docs require authentication.
- `paper_runtime.py` implements a one-cycle autonomous PAPER workflow: restart recovery -> terminal reconciliation -> deferred fee audit -> provider drift check -> closed-bar history -> fresh quote -> logical mark-to-market -> strategy -> Guardian/dynamic venue checks -> durable draft -> optional exactly-one paper POST. Default `allow_paper_submission=False` cannot POST.
- Provider drift guard rejects unexplained open orders, non-BTC positions, BTC quantity mismatch, inactive/blocked account or malformed buying power before new execution.
- Same signal/order ID cannot be posted twice; unresolved provider orders block new execution.
- Logical gains above the initial $100 no longer trip the old offline snapshot guard when—and only when—the snapshot is verified against Signal Vault's own persistent ledger. Untrusted >$100 offline snapshots remain rejected.
- `paper_worker.py` is an explicit one-cycle operator entry point. Paper POST is off by default and requires the exact `I_ACKNOWLEDGE_ALPACA_PAPER_ORDERS_ONLY` environment acknowledgement. Live-ish flags are rejected. The worker prints only sanitized logical metrics, not provider account IDs or secrets.
- `paper_smoke.py` remains a separate authenticated GET-only paper readiness command; it imports no executor.
- Current local checks: `make test` **116/116 PASS**, `make compile` PASS, `make demo` prints `DRY_RUN_RECORDED_NOT_FILLED`. No genuine provider call or paper fill has been performed.

## Limitations — never claim these are finished

- No real Alpaca paper credentials have been supplied; therefore account eligibility, actual response schemas, data entitlements/rate limits, BTC asset metadata, latest quote freshness and provider activity timing remain unverified in this account.
- No genuine authenticated historical dataset has been collected by Signal Vault and no real broker paper order has been submitted. All network-bound lifecycle tests use fake transports.
- SQLite is still the local prototype ledger. Before unattended cloud paper operation, migrate transactional order/accounting state to PostgreSQL (or justify and harden a single-writer SQLite deployment), add process locking and fault tests.
- No long-running scheduler/service manager, private dashboard, notifications, hosted deployment or seven-day genuine broker-paper run yet.
- Current strategy is a deterministic baseline candidate, not a demonstrated trading edge. Passing software tests says nothing about profitability.
- No stocks, Kalshi/event-contract execution or real-money connector yet.
- API behavior and fees must be rechecked against provider metadata/docs immediately before authenticated paper use.

## Resume protocol

Read `PROJECT_STATUS.md`, `NEXT_STEPS.md`, `ARCHITECTURE.md` and `docs/API_PROVIDER_ASSUMPTIONS.md` from latest private GitHub `main`, verify remote head/tree, run `make test`, `make compile`, and `make demo`, then continue paper-only development. Do not enable or add live execution. Create and verify an exact-tree GitHub checkpoint before stopping a session.

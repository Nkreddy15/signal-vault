# Release gates, not marketing screenshots

## Phase 1 (current)

- [x] Versioned modular-monolith architecture and adapter contracts documented.
- [x] Fail-closed runtime: only local offline paper dry run can start.
- [x] Deterministic risk engine with explicit position, daily loss, drawdown and quote-age limits.
- [x] Dry-run broker records an approved proposal but never falsely reports fills.
- [x] Unit tests and GitHub Actions safety-check workflow authored.
- [x] Private GitHub remote exists; initial full source-tree SHA matched and remote is source of truth.

## Phase 2 — offline integration groundwork (current)

- [x] Strict source-attributed, contiguous, fully-closed historical bar ingestion with pagination and failure tests (mock transport).
- [x] Baseline EMA crossover, strict HOLD, next-open research backtester with transaction cost assumptions and explicit hypothetical reporting.
- [x] Read-only Alpaca paper host allowlist and tradability checks (mock transport only); non-executable order drafts reject $5 and unsupported precision/time-in-force.
- [x] Local durable offline draft-idempotency and additive reservation journal with immutable audit events; NOT a broker fill ledger.
- [x] Paper lifecycle pure state machine + persisted SQLite state (mock tests): unknown timeout never blind-retries, cumulative fills cannot regress, and terminal orders hold reserves until reconciliation. Genuine provider audit still pending.
- [x] Fully offline Scout/Strategist-to-Guardian-to-draft pipeline; no broker API write methods.
- [x] Chronological disjoint fixed-parameter research folds, synthetic-data tests, no future-candle leakage in backtest.

## Phase 2 — genuine broker paper mode (still pending)

- [ ] Verified Alpaca paper credentials configured through secrets, never checked in.
- [ ] BTC/USD asset metadata, min lot, market-data timestamp and price/quantity precision checked.
- [x] Paper-order POST code hard-pinned to one literal paper-host endpoint and tested exclusively with fake transports. **No authenticated actual paper POST yet.**
- [x] Idempotent place/lookup/partial-fill lifecycle, durable cash reservations, UNKNOWN_RESULT recovery and terminal reconciliation are implemented under fake transports. Provider-authenticated verification remains pending.
- [ ] Postgres state, fill reconciliation after restarts and audit trail.
- [ ] Historical baseline strategy with look-ahead-free backtest and after-cost accounting.
- [ ] Dashboard and daily report distinguish proposed, submitted, filled, paper and dry run.

## Phase 3 — operational validation (not started)

- [x] Single-instance runtime lock, secret-free atomic health file, local deduplicated alert hook, automatic UTC daily-risk session reset, clean scheduler cadence policy and fatal unexpected-exception halt are unit-tested.
- [ ] Fault tests: stale quotes, out-of-order stream, API timeouts, duplicate callbacks, restart, data gap, lost connectivity.
- [x] Local emergency halt, maximum new order, aggregate exposure, daily pause and drawdown pause are independently unit-tested; provider-integrated fault validation remains pending.
- [ ] Complete 7 uninterrupted days of **genuine broker paper** operation on a $100 logical allocation; no manual selection of trades.
- [ ] Every order matches its provider record; all portfolio discrepancies resolved.
- [ ] After-cost performance analysis and representative out-of-sample testing documented; extend paper testing if insufficient observations.
- [ ] Explicit owner review and approval before any real-money connector or activation.

**Important:** Seven profitable paper days are not proof of sustainable live alpha. Failing a gate moves the live date; quality and the paper-only authorization cannot be waived to hit November 1.

## Phase 2G offline operator & runtime safety (implemented, not deployed)

- [x] Private read-only operator snapshot and HTTP Basic token local monitor, fixed IPv4 loopback binding, no order POST or broker imports; 401/405 and no secret/event body leakage covered by offline tests.
- [x] Explicit owner-only journal initialization and preflight checks for permissions, corruption and low disk space.
- [x] SQLite consistent backup into an owner-only exclusive filename with integrity/hash checks; never auto-resume trading after restoration.
- [x] Guardian risk policy rejects invalid limits (NaN/Infinity/negative/string), invalid timing/identities/maps and cash+marked-position equity inconsistencies.
- [ ] Authenticated real Alpaca PAPER smoke, provider/fill evidence, seven-day runtime, PostgreSQL critical ledger and production deployment remain outstanding.

## Phase 2H PostgreSQL migration contract (unapplied)

- [x] Drafted isolated PAPER-only SQL schema with initial operator halt, NUMERIC ledger,
  append-only audit and DB-level unique unresolved paper order; static source tests pass.
- [ ] Actual PostgreSQL migration, Python transactional port, concurrent worker tests,
  crash/restart, fee/fill reconciliation and provider smoke remain not implemented.

## Phase 2I integration and safety (offline only)

- [x] Optional JSON-only public-feature AI veto cannot submit or override Guardian, defaults OFF and cannot veto risk-reducing SELL.
- [x] Optional offline logistic ML confirmation/artifact fingerprint/promotion receipt gate under fake/synthetic tests; not provider data or proof of edge.
- [x] Frozen chronological research protocols, source-labelled reporting, isolated data-capture interfaces and bounded READ-only retries under fakes.
- [x] Owner API 127.0.0.1:8765 and separate HTML read-only monitor :8766; status/resume cannot create missing journal.
- [x] 225/225 combined offline tests passing, compilation and offline dry-run PASS.
- [ ] Authenticated real PAPER provider schema/readiness, genuine dataset, seven-day actual paper execution and transactional Postgres port remain outstanding.

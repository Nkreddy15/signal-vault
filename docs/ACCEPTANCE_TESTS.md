# Release gates, not marketing screenshots

## Phase 1 (current)

- [x] Versioned modular-monolith architecture and adapter contracts documented.
- [x] Fail-closed runtime: only local offline paper dry run can start.
- [x] Deterministic risk engine with explicit position, daily loss, drawdown and quote-age limits.
- [x] Dry-run broker records an approved proposal but never falsely reports fills.
- [x] Unit tests and GitHub Actions safety-check workflow authored.
- [ ] New private GitHub remote exists and initial commit is pushed. Requires a blank private repository created by the user (current connector cannot create repos).

## Phase 2 — genuine broker paper mode (not started)

- [ ] Verified Alpaca paper credentials configured through secrets, never checked in.
- [ ] BTC/USD asset metadata, min lot, market-data timestamp and price/quantity precision checked.
- [ ] Network order host hard-pinned to paper endpoint; test refuses anything else.
- [ ] Idempotent place/lookup/cancel/partial-fill lifecycle and durable cash reservations.
- [ ] Postgres state, fill reconciliation after restarts and audit trail.
- [ ] Historical baseline strategy with look-ahead-free backtest and after-cost accounting.
- [ ] Dashboard and daily report distinguish proposed, submitted, filled, paper and dry run.

## Phase 3 — operational validation (not started)

- [ ] Fault tests: stale quotes, out-of-order stream, API timeouts, duplicate callbacks, restart, data gap, lost connectivity.
- [ ] Emergency halt, maximum new order, aggregate exposure, daily pause and drawdown pause independently verified.
- [ ] Complete 7 uninterrupted days of **genuine broker paper** operation on a $100 logical allocation; no manual selection of trades.
- [ ] Every order matches its provider record; all portfolio discrepancies resolved.
- [ ] After-cost performance analysis and representative out-of-sample testing documented; extend paper testing if insufficient observations.
- [ ] Explicit owner review and approval before any real-money connector or activation.

**Important:** Seven profitable paper days are not proof of sustainable live alpha. Failing a gate moves the live date; quality and the paper-only authorization cannot be waived to hit November 1.

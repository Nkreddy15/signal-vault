# Phase 2-F test report (2026-09-28)

- Run `make smoke` from root with Python 3.11+; pure stdlib in initial build.
- 130 offline `unittest` checks passing at the saved development checkpoint.
- `make fake-scenario` exercises fake-only accepted -> terminal -> three-way
  source evidence -> reconciled. Absolutely ZERO authenticated Alpaca requests,
  zero real Alpaca paper fills, zero live-money trades, zero deployment.
- Coverage added: submitted-draft void exploit prevention, account/position
  evidence mismatch, unexpectedly changed provider order, same-account paper
  preflight, dynamic venue min sizing, quote staleness, initial $100 isolated
  virtual budget, external account contamination, persistent operator HALT,
  loopback-only read-only dashboard, input fuzz regressions and fake complete
  order lifecycle.
- Additional offline tests: explicit paper-account GET-only onboarding,
  source venue minimum/step and dust-sell preview, once-per-bar unarmed
  research supervisor with stale-input and worker-lock tests, agent-decision
  schema rejects order/tool overrides, unsent draft TTL protections.
- Source-driven virtual risk marks: persistent high-water drawdown pause,
  UTC-day rollover, source mark conflict rejection and prohibition of fabricated
  paper profits exceeding the original $100 allocation.
- Additional Phase 2-F coverage: redacted sandbox-only credentials, cross-
  account read-blocking and restarted UNKNOWN->terminal->independently-audited
  recovery, all tested with FAKE provider responses and no actual HTTP.
- Remaining tests prior to pilot: actual provider paper integration (requires
  separately approved paper credentials), true venue fee precision and
  multi-order cash/BTC reconciliation, property/fault tests, authenticated
  dashboard, worker/restart endurance, performance against selected baseline,
  seven full days of autonomous real provider paper operation.
- Profitability: NOT TESTED or demonstrated. Research backtests remain
  hypothetical and the fake provider events are explicitly labeled simulated.

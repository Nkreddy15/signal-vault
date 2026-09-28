# Signal Vault — Phase 2-B local engineering test report

Date: September 28, 2026. Testing is fully OFFLINE, using synthetic fixture candles and fake paper GET responses. Tests do not imply live profitability, genuine Alpaca paper fills, a cloud deployment, or independent security certification.

- Python standard library unittest; command `make test`.
- Expected current suite: **74 tests** across runtime, Guardian, dry-run broker, market data, strategy/backtest, chronological folds, mock paper read-only adapter, non-executable order draft, offline journal, offline pipeline, and pure + persisted paper order state machine, one-attempt paper writer using fake transports only.
- `make demo`: local proposal $15 BTC/USD, must return `DRY_RUN_RECORDED_NOT_FILLED`.
- `SIGNAL_VAULT_MODE=live make demo` must error before any external action.
- Market data rejects NaN/negative prices, inconsistent OHLC, invalid timezone, out-of-order/missing hours, incomplete/future bars and broken pagination.
- Backtester models fixed-parameter strategy on completed previous bars and places hypothetical fills only at the next bar's OPEN; cost estimates and open marks explicit.
- Unknown provider order result cannot retry blindly; terminal observation cannot bypass account/position/order reconciliation.
- Alpaca paper boundary contains only allowlisted GETs pinned to the paper host; no POST, withdrawals or transfers; test mocks only.
- Production gaps: no verified market data dataset, no authenticated paper broker integration, no persistent **provider** order/fill ledger, no deployment/continuous scheduler. Forward paper testing has not started.

Official provider assumptions and re-verification obligations: `docs/API_PROVIDER_ASSUMPTIONS.md`.

Phase 2-C: an optional paper-host-only POST function now exists; default CLI and tests do NOT contact a broker. A malformed/timeout response holds reserves in UNKNOWN_RESULT, and duplicate calls cannot cause a second POST. Actual paper provider integration, independent audit and cloud deployment are still pending.

Restart simulation also verifies pre-crash submission state is persisted and demoted to UNKNOWN, requiring a paper GET lookup; known accepted/partial orders may be polled without resubmission. All such tests use local mocks.

# Exact recovery / implementation sequence

1. GitHub `main` is the authoritative current source at https://github.com/Nkreddy15/signal-vault. Read `PROJECT_STATUS.md`, `ARCHITECTURE.md`, and this document from GitHub, then run `make test` after checking out the latest commit.
2. Confirm expected base tree/commit before writes. Phase 1 source tree `78f21d5eafbea9a70fc60fadcbbeae85a10cb099` was verified identical on GitHub. Do not re-import the original archived snapshot over newer changes.
3. Phase 2: implement versioned market data, ATR/EMA or another explicitly defined baseline candidate strategy, walk-forward backtest with realistic costs and a strict HOLD state. No promises of returns.
4. Add **Alpaca paper-only** SDK adapter with pinned endpoint, separate sandbox credentials, fresh asset metadata and `BTC/USD` valid GTC/IOC orders. Do not accept any `live` flag. Check symbol minimum order size — do not upscale a small $5 proposal to satisfy the provider automatically.
5. Add durable Postgres persistence, idempotent submission state machine, reserve/release pending capital, order lookup before timeout retry, fill and balance reconciliation and risk controller integration. Add failure-injection and security tests.
6. Add private authenticated owner dashboard, operator halt, cost/after-fee metrics, notifications and deployment manifests. Deployment requires user approval and an authorized cloud account.
7. Begin genuine paper trading for seven days minimum only after a fault-tested paper broker adapter and cloud runtime exist; then inspect stability, costs and performance. No real-money access or orders without new explicit owner approval and a separate reviewed release.

**Resumption prompt:** `Continue Signal Vault from the latest saved GitHub/Library checkpoint. Read PROJECT_STATUS.md and NEXT_STEPS.md, run tests, and maintain paper-only mode. Do not enable live trading.`

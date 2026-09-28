# SIGNAL VAULT

**Phase 1 — architecture checkpoint and offline paper-only safety kernel**

Signal Vault is intended to become an autonomous, independently hosted multi-market research, risk and execution platform. The *first enabled integration* will be BTC/USD in **Alpaca paper trading**. Equity and event-contract adapters are future work; they are not simulated by silently treating their instruments as Bitcoin.

## Current state (2026-09-28)

This first Git checkpoint contains an architecture, development and security plan, a venue-aware trading intent model, a fail-closed deterministic pre-order risk engine, a fully offline dry-run recorder, a database design, and repeatable tests. **It does not yet connect to Alpaca, host a dashboard, place paper brokerage orders, or execute live-money trades.** Do not represent dry-run receipts as fills or P&L.

### Safe local smoke test

Python 3.11+ is sufficient; no API keys or paid services are needed.

```sh
python3 -m venv .venv
source .venv/bin/activate
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m signal_vault
```

Expected demo status: `DRY_RUN_RECORDED_NOT_FILLED`. That is an offline record, not a broker order. Optionally run `make test` and `make demo`.

To verify the fail-closed lock:

```sh
SIGNAL_VAULT_MODE=live PYTHONPATH=src python -m signal_vault
# Must exit with ValueError: Phase 1 is PAPER ONLY.
```

## Reading order for resuming work

1. `PROJECT_STATUS.md` — authoritative completed work / known blockers.
2. `NEXT_STEPS.md` — exact next development sequence.
3. `ARCHITECTURE.md` — boundaries, contract design, failure behavior.
4. `docs/SECURITY.md` and `docs/ACCEPTANCE_TESTS.md`.
5. `docs/DELIVERY_PLAN.md` — October schedule toward the November 1 **conditional** pilot target.

## No secrets, no account changes

Do not commit `.env`, tokens, wallet keys or broker credentials. User approval is required before account access, paid services, deployment, or any transition from simulated/paper to real-money execution. There is deliberately no live broker connector in this repository.

## External API references to validate during Phase 2

- [Alpaca paper trading](https://docs.alpaca.markets/us/docs/paper-trading)
- [Alpaca crypto orders](https://docs.alpaca.markets/us/docs/crypto-orders): crypto supports `gtc`/`ioc`; do **not** reuse equity-only `day` assumptions.
- [Alpaca trading order IDs](https://docs.alpaca.markets/us/docs/working-with-orders)

The broker-adapter implementation must validate actual asset minimum order sizes, price/quantity increments, account eligibility, data entitlements and fees against the provider at runtime.

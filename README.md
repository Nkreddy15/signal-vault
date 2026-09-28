# SIGNAL VAULT

**Phase 2-C — offline research plus guarded paper-only submission implementation (NOT activated)**

Signal Vault is intended to become an autonomous, independently hosted multi-market research, risk and execution platform. The *first enabled integration* will be BTC/USD in **Alpaca paper trading**. Equity and event-contract adapters are future work; they are not simulated by silently treating their instruments as Bitcoin.

## Current state (2026-09-28)

The current checkpoint includes the initial architecture and safety kernel plus a strict public historical BTC/USD bar adapter (not yet used against the real provider), a versioned deterministic strategy, a cost-aware OFFLINE backtest, a paper-host GET-only account/asset/order lookup adapter (mock-tested, not authenticated), and a persistent SQLite draft/audit foundation, a persisted conservative paper order state machine, chronological research folds, an end-to-end offline planning pipeline and a single-attempt paper-only order writer (mock-tested, NOT run with actual credentials). **It does not yet connect to an authenticated Alpaca account, submit genuine paper orders, host a dashboard, or execute live-money trades.** Never represent offline research fills as provider paper fills or P&L.

### Safe local smoke test

Python 3.11+ is sufficient; no API keys or paid services are needed.

```sh
python3 -m venv .venv
source .venv/bin/activate
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m signal_vault
```

Expected demo status: `DRY_RUN_RECORDED_NOT_FILLED`. The example $15 buy is only an offline record, not a broker order. Optionally run `make test`, `make demo`, `make compile`. The *research-only* CLI is `PYTHONPATH=src python -m signal_vault.backtest PATH_TO_REAL_UTC_HOURLY_CSV --as-of 2026-09-28T00:00:00Z` (replace with a verified data file and a timestamp after its last fully closed bar). It will label all results hypothetical and contains no network orders. Add `--fold-hours 168` for fixed-parameter chronological research folds; this is not proof of independent live performance.

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

Do not commit `.env`, tokens, wallet keys or broker credentials. User approval is required before account access, paid services, deployment, or any transition from simulated/paper to real-money execution. There is deliberately NO LIVE broker connector. `paper_executor.py` contains a hardcoded **paper-host-only** POST that is NOT called by the CLI, only after an approved draft has been durably moved to `SUBMISSION_PENDING`; all external integration tests use fakes. Real paper POST requires explicit separate paper credentials and operator setup; no account has been connected or order sent in this checkpoint.

## External API references and assumptions

- [Alpaca paper trading](https://docs.alpaca.markets/us/docs/paper-trading)
- [Alpaca crypto orders](https://docs.alpaca.markets/us/docs/crypto-orders): crypto supports `gtc`/`ioc`; do **not** reuse equity-only `day` assumptions.
- [Alpaca trading order IDs](https://docs.alpaca.markets/us/docs/working-with-orders)

The broker-adapter implementation must validate actual asset minimum order sizes, price/quantity increments, account eligibility, data entitlements and fees against the provider at runtime.

See [`docs/API_PROVIDER_ASSUMPTIONS.md`](docs/API_PROVIDER_ASSUMPTIONS.md) for checked provider constraints and why the paper-development defaults were revised to a $15 maximum buy / $30 aggregate exposure; those values are not preapproved for live trading.

## Source handoff contingency (private repo only)

If the ChatGPT Library-to-GitHub source transfer is unavailable, download the **latest complete checkpoint ZIP** from `/Signal Vault/` in your Library and extract it on your Mac (including `.git`). Then run `bash signal-vault/scripts/publish_private_checkpoint.sh` from the extracted parent directory, or run the script by absolute path. It verifies the existing private remote history, ensures unexpected collaborator code changes are not overwritten, asks you to type `PUBLISH`, and uses an ordinary fast-forward Git push (never force). Requires your Mac to have Git, Python 3, and GitHub authentication. This publishes CODE ONLY: no Alpaca connection, purchases, orders or deposits.

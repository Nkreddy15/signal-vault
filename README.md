# SIGNAL VAULT

**Phase 2-F — unattended paper-runtime hardening (provider credentials/order submission NOT activated)**

Signal Vault is intended to become an autonomous, independently hosted multi-market research, risk and execution platform. The *first enabled integration* will be BTC/USD in **Alpaca paper trading**. Equity and event-contract adapters are future work; they are not simulated by silently treating their instruments as Bitcoin.

## Current state (2026-09-28)

The repository now contains the modular architecture, deterministic Guardian, authenticated fixed-host market-data readers, logical $100 portfolio ledger, persistent paper order lifecycle, fill/fee/position reconciliation, restart recovery, provider-drift checks, a one-cycle autonomous paper runtime, and a hardened single-instance scheduler shell with local health/alert files and durable operator halt controls. The runtime is extensively fake-transport tested but **has not been authenticated against the user's Alpaca paper account and has not sent a genuine paper order**. The default CLI remains offline and non-filling. Real-money execution does not exist.

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


### Unattended paper shell (not yet connected)

`paper_daemon.py` is the long-running **paper-only** scheduler shell. It uses an owner-only filesystem lock so a second worker cannot operate the same SQLite journal, writes an atomic secret-free health snapshot, emits local state-transition alerts without provider payloads, rechecks a persistent operator halt, and fails closed on unexpected runtime exceptions. It still requires Alpaca PAPER credentials for authenticated reads, and it cannot select a live host. Paper POST remains disabled unless the exact paper-only acknowledgement is supplied.

Local operator controls require no broker network access:

```sh
SIGNAL_VAULT_PAPER_DB=./data/signal-vault-paper.sqlite3 PYTHONPATH=src python -m signal_vault.control halt --reason "operator maintenance"
SIGNAL_VAULT_PAPER_DB=./data/signal-vault-paper.sqlite3 PYTHONPATH=src python -m signal_vault.control status
SIGNAL_VAULT_PAPER_DB=./data/signal-vault-paper.sqlite3 PYTHONPATH=src python -m signal_vault.control resume
```

Do not run `paper-daemon` until the authenticated read-only smoke gate is completed.

## Phase 2G: private PAPER operator monitoring and local reliability

The code now includes `operator_server.py` and `operator_view.py` (loopback-only,
HTTP Basic-authenticated, read-only local dashboard and JSON state),
`preflight.py` (owner/file mode/disk/integrity/ledger checks), `init_paper.py`
(explicit local $100 paper journal initialization), and `local_backup.py`
(consistent exclusive owner-only SQLite snapshot). The local SQLite journal
now creates/tightens its primary file mode to 0600 before opening it. The
`ops/systemd` service units are **uninstalled templates**, not deployed services.
See `docs/OPERATOR_MONITOR.md` and `docs/DEPLOYMENT_PREPARATION.md`.
No Alpaca authenticated interaction or real brokerage paper fill has occurred.

## Reading order for resuming work

1. `PROJECT_STATUS.md` — authoritative completed work / known blockers.
2. `NEXT_STEPS.md` — exact next development sequence.
3. `ARCHITECTURE.md` — boundaries, contract design, failure behavior.
4. `docs/SECURITY.md` and `docs/ACCEPTANCE_TESTS.md`.
5. `docs/DELIVERY_PLAN.md` — October schedule toward the November 1 **conditional** pilot target.

## No secrets, no account changes

Do not commit `.env`, tokens, wallet keys or broker credentials. User approval is required before account access, paid services, deployment, or any transition from simulated/paper to real-money execution. There is deliberately NO LIVE broker connector. `paper_executor.py` contains a hardcoded **paper-host-only** POST that is NOT called by the CLI, only after an approved draft has been durably moved to `SUBMISSION_PENDING`; all external integration tests use fakes. Real paper POST requires explicit separate paper credentials and operator setup; no account has been connected or order sent in this checkpoint. `paper_worker.py` can only POST to Alpaca PAPER after a separate exact acknowledgement variable is configured; it contains no live host.

## External API references and assumptions

- [Alpaca paper trading](https://docs.alpaca.markets/us/docs/paper-trading)
- [Alpaca crypto orders](https://docs.alpaca.markets/us/docs/crypto-orders): crypto supports `gtc`/`ioc`; do **not** reuse equity-only `day` assumptions.
- [Alpaca trading order IDs](https://docs.alpaca.markets/us/docs/working-with-orders)

The broker-adapter implementation must validate actual asset minimum order sizes, price/quantity increments, account eligibility, data entitlements and fees against the provider at runtime.

See [`docs/API_PROVIDER_ASSUMPTIONS.md`](docs/API_PROVIDER_ASSUMPTIONS.md) for checked provider constraints and why the paper-development defaults were revised to a $15 maximum buy / $30 aggregate exposure; those values are not preapproved for live trading.

## Source handoff contingency (private repo only)

If the ChatGPT Library-to-GitHub source transfer is unavailable, download the **latest complete checkpoint ZIP** from `/Signal Vault/` in your Library and extract it on your Mac (including `.git`). Then run `bash signal-vault/scripts/publish_private_checkpoint.sh` from the extracted parent directory, or run the script by absolute path. It verifies the existing private remote history, ensures unexpected collaborator code changes are not overwritten, asks you to type `PUBLISH`, and uses an ordinary fast-forward Git push (never force). Requires your Mac to have Git, Python 3, and GitHub authentication. This publishes CODE ONLY: no Alpaca connection, purchases, orders or deposits.

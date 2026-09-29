# SIGNAL VAULT

**Phase 2O — three owner-verified observations, isolated evidence snapshot and offline recovery drills; broker PAPER POST/live NOT activated**

Signal Vault is intended to become an autonomous, independently hosted multi-market research, risk and execution platform. The *first enabled integration* will be BTC/USD in **Alpaca paper trading**. Equity and event-contract adapters are future work; they are not simulated by silently treating their instruments as Bitcoin.

## Current state (2026-09-29)

The repository contains the modular architecture, deterministic Guardian, authenticated fixed-host market-data readers, logical $100 portfolio ledger, persistent paper order lifecycle, fill/fee/position reconciliation, restart recovery, provider-drift checks, a one-cycle paper runtime and a single-instance scheduler shell with operator halt controls. The owner reports successful LOCAL authenticated Alpaca PAPER account/quote READ-only smoke and SHA-verified historical captures; credentials have NOT been sent through chat/GitHub. v0.1, v0.2 and v0.3 failed their offline research gates and are NOT approved for paper-order submission. No genuine provider PAPER order, live order, deposit, paid deployment or real-money execution has occurred. The default CLI remains offline and non-filling.

### Current offline research and manual observation MVP

The fixed v0.1/v0.2/v0.3 candidate history and negative after-cost results are
recorded in `docs/RESEARCH_V02.md`, `docs/RESEARCH_V03.md` and
`PROJECT_STATUS.md`. The reserve post-gap period remains unexamined for
v0.2/v0.3; do not use it to rescue failed development candidates.

For a self-contained, fixed $15 BTC hypothetical round-trip cost audit, run
`PYTHONPATH=src python -m signal_vault.research_economics`. The owner reports
successful real authenticated **GET-only** `forward_capture`, zero-observation
`forward_observer` bootstrap, first hourly append at 05:05:56Z, and the first
real one-command `manual_forward_cycle` append at 06:03:59Z; journal count **2**,
no broker order or scheduler. Existing capture
CSV + source SHA manifest + SQLite journal stay local and Git-ignored under
`data/forward/`.

**Phase 2K usability improvement:** `PYTHONPATH=src python -m
signal_vault.manual_forward_cycle` makes a safe, *single manual invocation*
out of next-hour GET capture, verification and exactly-one new observation.
It validates the already-bootstrapped journal's precise next consecutive UTC
close **before prompting for local hidden PAPER DATA keys**, and only runs
during UTC minute 03–24. A missed hour, repeated current hour, stale/altered
capture, or concurrent cycle fails closed; it never backfills or bootstraps
silently. A new segment must first be created explicitly with the original
`forward_capture` + `forward_observer --bootstrap --db
data/forward/observations-segment-02.sqlite3`. Only then may one-command
mode specify the existing `--db` segment. The new feature is fake-provider
CI-tested but has not yet been run against the owner's real provider. No
scheduler, strategy signals, order POST or live connector is enabled. See
`docs/FORWARD_OBSERVATIONS.md` for safe operator commands and incident handling.

### Safe local smoke test

Python 3.11+ is sufficient; no API keys or paid services are needed.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[research]'
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

## Phase 2I: combined offline research and operator groundwork

The project includes a strict research/ML confirmation path, bounded optional
LLM advisory with no default API client, source-labelled reporting, validated
local backups and two distinct loopback control surfaces: a **read-only** HTML
monitor on 127.0.0.1:8766 and a separately authenticated **paper HALT/resume
only** JSON control API on 127.0.0.1:8765. No live orders, real paper orders or
provider API credentials have been used. All 225 local offline tests passed at
the Phase 2I checkpoint. See `PROJECT_STATUS.md` for current actual gates.

## Phase 2H: isolated PostgreSQL PAPER critical-ledger design

`db/migrations/0002_critical_paper.sql` and `docs/POSTGRES_PAPER_LEDGER.md`
provide an **unapplied schema/transaction contract**, not a working Postgres
adapter. It fails closed with an initial operator HALT, exact money types,
append-only audit constraints and at most one unreconciled order. No production
Postgres or live trading integration is connected. The current runnable storage
remains the single-host SQLite PAPER prototype until a real tested port exists.

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

## Phase 2L: local evidence audit without altering ongoing capture

`PYTHONPATH=src python -m signal_vault.forward_evidence_audit` is a fully
offline **SQLite read-only forensic check** of the owner-local
`data/forward/observations.sqlite3` journal and its standard captured
CSV/manifest files. It reconstructs the original 72-hour bootstrap hashes
and every later prospectively observed hour; verifies source labels, raw CSV
SHA-256s, expected UTC-hour windows, immutable overlapping candles, captured
vs observed chronology and the stored 6h/24h/range/cost calculations.
It checks SQLite integrity and compares the entire reconstructed anchored
hash table to the persisted one. For separate segments, use
`--db data/forward/observations-segment-02.sqlite3`.

Unlike the collector, the auditor is intentionally suitable for older
archives: it checks their **original** capture timestamps rather than
pretending aged captures can count as new future observations. Its pass
means **internal unsigned local-evidence consistency only**, not independent
Alpaca attestation, profitability, filled trades or an unseen model holdout.
No provider request, credentials, SQLite journal mutation, orders, daemon or
deployment is involved. See `docs/FORWARD_OBSERVATIONS.md`.

## Phase 2M: check the next collection window WITHOUT credentials

For an explicit preflight at any time (including before the next UTC hour),
run `PYTHONPATH=src python -m signal_vault.forward_readiness`. It performs
the full offline Phase 2L archived-evidence audit, reads the recorded most
recent anchored hour, and returns an exact UTC next-hour capture window and
clear WAIT / READY / EXISTING_CAPTURE / MISSED / HALT status. It never asks
for keys, calls Alpaca, writes SQLite, recaptures a preexisting filename,
schedules anything or generates orders. It separately distinguishes an
already-captured yet fresh hour from a new hour eligible for the manual
collector, preventing accidental re-capture after an append error. Named
existing segments use `--db data/forward/observations-segment-02.sqlite3`.

A readiness result is ONLY a timing and local-evidence assessment, not proof
of provider availability, tradability or predictive performance. Actual
collection remains a separate, deliberate
`PYTHONPATH=src python -m signal_vault.manual_forward_cycle` invocation.
The user-local Python editable-install output `*.egg-info/` is now Git-ignored.

## Phase 2N: snapshot and isolated verification of exploratory evidence

The owner-reported local forward journal contains **two** actual chronological
market DATA observations; its separate `forward_readiness` internal evidence
audit passed before the second. A full owner-side post-second-observation
`forward_evidence_audit` result is still awaited; do NOT claim it has run.

`PYTHONPATH=src python -m signal_vault.forward_snapshot --create` is a new,
**manual, offline** utility that first requires the source journal and all
its archived genuine CSV/manifest data to pass the complete independent
read-only consistency audit. It then uses a consistent SQLite online backup,
copies only original captures referenced by that snapshotted journal into a
separate private local folder, and verifies the copied chain before publishing
a never-reused snapshot name. It does not replace, reset or restore over the
active journal. A printed snapshot basename may later be checked offline via
`PYTHONPATH=src python -m signal_vault.forward_snapshot --verify <NAME>`.
The local snapshot SHA manifest is **unsigned, unencrypted, same-device**
evidence, not an offsite disaster-recovery solution or provider attestation.
Source files and backups are Git-ignored under `data/forward/`. Full procedure:
`docs/FORWARD_SNAPSHOTS.md`. No orders, funding, credentials or scheduler.

## Phase 2O — local scratch recovery drill

The owner repeated the Phase 2N snapshot verification successfully. The new `forward_recovery_drill.py` checks the saved snapshot, copies it into temporary private folders, verifies that the isolated chain can be read, and checks that four separately damaged test copies are rejected. The original journal and original snapshot are not modified. Run the command only after pulling current main; see `docs/FORWARD_RECOVERY_DRILL.md`. This is an offline, same-device rehearsal, not a production restore.

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

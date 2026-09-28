# Signal Vault

Private, modular autonomous trading engineering project. The initial venue is
**Alpaca BTC/USD PAPER only**. Stock and event-contract adapters remain future
components of the same architecture, not secretly enabled alternatives.

## Current release: Phase 2-E (offline-tested prototype)

- Strict hourly BTC historical data handling, immutable deterministic signals,
  research-only next-open backtesting with explicit hypothetical costs.
- Guardian risk limits; SQLite drafts, cash reservations, order-ID uniqueness,
  restart-safe UNKNOWN transport states and paper-host-bound source checks.
- Pre-submission independent paper account snapshot, dynamic provider minimum
  quantity/precision checks, post-terminal fee-aware order/cash/BTC reconciliation.
- Separate virtual $100 budget, fixed $30 marked exposure, UTC-session/peak
  equity marks and manual persistent emergency HALT across process restarts.
- Unarmed research supervisor with persistent once-per-closed-bar decisions and
  expiration of strictly unsubmitted stale drafts (never release a paper order).
- Venue-specific BTC minimum/step checks and honest dust-aware SELL preview.
- A strictly parsed optional AI selection gate that may choose HOLD or an
  existing evidence-bound signal, never allocate capital or override Guardian.
- LOCAL READ-ONLY dashboard. Never expose to the internet without an entirely
  separate authentication and deployment security review.

**No Alpaca account has been connected; no authenticated paper orders or real
money orders were placed; no profits are claimed.** All network-capable order
code is in a separate paper-only adapter and the default CLI never invokes it.

### Run self-contained engineering tests (Python 3.11+)

```bash
python3 -m venv .venv && source .venv/bin/activate
make smoke
```

`make fake-scenario` runs an explicitly FAKE venue through one accepted ->
filled -> reconciled lifecycle. It uses mock credentials and in-memory data, no
HTTP requests, and is not evidence of Alpaca paper execution.

### Optional LOCAL operator view (creates no broker account or orders)

```bash
make init-local       # creates NEW .data/offline-paper.sqlite3; will not overwrite
make local-dashboard  # open http://127.0.0.1:8765 on this same computer
PYTHONPATH=src python -m signal_vault.operator --db .data/offline-paper.sqlite3 status
PYTHONPATH=src python -m signal_vault.operator --db .data/offline-paper.sqlite3 halt --reason "owner emergency stop"
PYTHONPATH=src python -m signal_vault.operator --db .data/offline-paper.sqlite3 resume --reason "incident reviewed"
```

The dashboard has NO account, funding, order or mutation endpoints. HALT blocks
**new** submissions; it does not cancel an order already received by an external
broker. Unknown orders must be reconciled before clearing HALT.

### Other developer commands

- `make test`: offline unittest suite.
- `make demo`: guarded dry-run proposal, never a fill.
- `make compile`: compile src/tests.
- `make fake-scenario`: one complete deliberately simulated paper lifecycle.
- `PYTHONPATH=src python -m signal_vault.research_runner --db .data/offline-paper.sqlite3 --csv REAL_UTC_HOURLY.csv --as-of 2026-09-28T06:00:03Z`: local, unarmed research replay; no broker orders or authenticated calls.
- `PYTHONPATH=src python -m signal_vault.research_runner --db .data/offline-paper.sqlite3 --public-data --confirm-read-only-market-data`: optional read-only public Alpaca market-data request, may need account entitlement; NEVER POSTs orders.
- `PYTHONPATH=src python -m signal_vault.paper_onboarding --confirm-paper-read-only`: optional *authenticated GET-only* paper-account eligibility check, requires separate local `SV_ALPACA_PAPER_KEY` and `SV_ALPACA_PAPER_SECRET` environment variables; do not paste either into this chat or commit them.
- `SIGNAL_VAULT_MODE=live make demo`: must be explicitly rejected.

Research-only backtests can be invoked via
`PYTHONPATH=src python -m signal_vault.backtest PATH_TO_VERIFIED_UTC_HOURLY_CSV --as-of 2026-09-28T00:00:00Z`.
Use a real, time-stamped dataset and an as-of value after the final closed bar.
Never label backtest proceeds as broker-confirmed profits.

Read `PROJECT_STATUS.md` and `NEXT_STEPS.md` before editing, especially after a
ChatGPT usage reset. `ARCHITECTURE.md`, `docs/SECURITY.md` and
`docs/API_PROVIDER_ASSUMPTIONS.md` document the hard constraints.

### Secret and account rules

No live-trading endpoint or switch exists. Do not commit tokens or paste broker
API secrets into chat; use a separate authorized secret process when testing a
real Alpaca PAPER account. A future Nov 1, 2026 $100 live pilot is conditional
on validated broker paper runs, reliable operation and new explicit owner approval.

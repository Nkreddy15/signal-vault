# SIGNAL VAULT — durable project checkpoint

**Checkpoint:** PHASE2-2026-09-28-D — integrated fake PAPER lifecycle and local
operator controls; all real-money execution disabled.
**Repository:** private https://github.com/Nkreddy15/signal-vault, `main`.
Phase 2-C remote exact source tree SHA `b9feceab2cbefdb998d642cdb22d81685cf51ed3`
was imported as GitHub commit `763e47ec87daf9b7b66546f2f2a2aaf32b1af297`.
Phase 2-D source is tracked in the local working tree and must be synchronized
as a separate fast-forward checkpoint (verify actual remote commit after upload).
**Authorization:** engineering and offline paper-only tests. No deposits,
paid services, broker credentials, authenticated requests, genuine paper broker
orders, live orders or hosting deployed. November 1 is a conditional milestone.

## Completed and locally tested

- Venue-neutral architecture, immutable trade identity, fail-closed Guardian,
  strict BTC/USD UTC hourly data validation, research-only next-open backtesting
  and deterministic EMA baseline with documented cost assumptions.
- Alpaca paper-only GET reader and exact single-attempt PAPER POST adapter code
  (not activated against a real account). Draft order requires immutable quote
  price, must be recent and must satisfy runtime asset minimum quantity and
  cash-only source preflight before `SUBMISSION_PENDING` is persisted.
- SQLite order/draft lifecycle, crash-safe UNKNOWN state, no duplicate broker
  order POST after uncertainty, append-only event audit and explicit terminal
  reconciliation; submitted drafts cannot be voided to release their reserves.
- Source-evidence reconciler compares the confirmed broker order with durable
  pre-submission PAPER account cash/BTC baseline and post-submission account
  holdings, allowing limited receive-currency fee deductions. Caller-provided
  success booleans are no longer a valid release mechanism.
- A separate virtual $100 ledger ignores Alpaca's default paper balance,
  records only independently reconciled broker USD/BTC changes and refuses
  externally modified account balances, oversize aggregate long exposure and
  an observed virtual balance loss of $3 or more from the initial $100.
- Persistent operator emergency HALT and explicit local CLI; local-only,
  read-only monitoring dashboard with safe text rendering, Host checking and
  no account-changing endpoints.
- `make fake-scenario` demonstrates a FAKE, offline accepted -> filled ->
  reconciled order against injected fake GET/POST responses; absolutely no
  claimed Alpaca fills, authenticated requests or real trading performance.
- `make test`: **101/101 offline tests PASS** at this checkpoint, `make demo`
  remains local, and no actual trading advantage has been established.

## Honest blockers

- No user Alpaca paper credentials, real public historical market dataset,
  authenticated broker tests, deployed scheduler, authenticated cloud UI,
  cloud runtime, messaging integration or seven-day provider paper run.
- The true daily reset/high-water risk ledger, independent live-venue fee
  reconciliation, a venue-accurate sellable-quantity/dust policy and a
  source-backed paper proposal method remain mandatory before unattended
  broker operation. The virtual ledger currently guards submission exposure,
  but caller-provided research snapshots are not a production input.
- The current dashboard must NOT be internet-exposed. It binds to 127.0.0.1;
  cloud hosting requires authentication, HTTPS and a deployment/security audit.
- No live-money API route is implemented. A paper run cannot prove durable
  positive expected returns; Nov 1 transition must remain conditional.

## Resume instructions

Read this file, `NEXT_STEPS.md`, `ARCHITECTURE.md` and `docs/SECURITY.md`
from the newest *verified* private GitHub `main` checkpoint. Run `make smoke`
before edits, and document exactly which artifact or remote SHA is being
advanced. Preserve separate paper and future live deployment contracts; never
place secrets in Git or the source manifest.

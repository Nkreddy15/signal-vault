# SIGNAL VAULT — durable project checkpoint

**Checkpoint:** PHASE2-2026-09-28-E — unarmed research scheduler and explicit paper onboarding added to fake PAPER lifecycle and local
operator controls; all real-money execution disabled.
**Repository:** private https://github.com/Nkreddy15/signal-vault, `main`.
Phase 2-C remote exact source tree SHA `b9feceab2cbefdb998d642cdb22d81685cf51ed3`
was imported as GitHub commit `763e47ec87daf9b7b66546f2f2a2aaf32b1af297`.
Phase 2-D code was verified and imported at remote commit
`dd459e103158f4ed3e44550cc1951ee0b6022be5`, source tree
`1735b2d186218042acd4729a79a9539ecf38ae43`. A subsequent remote
status-only commit was `a04dfdf5bb5aebf084eeba33a80d7fbfdf47756a`.
Phase 2-E code must be imported and verified as another normal fast-forward;
never assume Library source is already synchronized without the exact tree check.
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
- Phase 2-E: current provider minimum/quantity step parser and non-executable
  dust-preserving sell preview; strictly unarmed once-per-hour research cycle
  with local OS worker lock, stale quote rejection, crash restart/TTL protections;
  read-only paper-account onboarding requiring an explicit owner confirmation
  and environment-supplied paper credentials; constrained, evidence-bound AI
  candidate-selection schema (no model provider currently connected).
- Validated virtual mark-to-market high-water and UTC daily-equity baselines;
  source-validated hourly marks now feed Guardian and independently guard paper
  submissions. Legitimately proven paper gains above $100 cannot be confused
  with caller-fabricated balances.
- `make test`: **124/124 offline tests PASS** at this checkpoint, `make demo`
  remains local, and no actual trading advantage has been established.

## Honest blockers

- No user Alpaca paper credentials, real public historical market dataset,
  authenticated broker tests, deployed scheduler, authenticated cloud UI,
  cloud runtime, messaging integration or seven-day provider paper run.
- Read-only market marks and true daily/peak ledger are now implemented;
  independent live-venue fee precision, a venue-accurate sellable-quantity/dust
  policy and an end-to-end source-backed production paper proposal method
  remain mandatory before unattended broker operation. The virtual ledger currently guards submission exposure,
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

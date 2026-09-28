# SIGNAL VAULT — durable project checkpoint

**Checkpoint:** PHASE2-2026-09-28-F (integrated recovery and credential hardening) — unarmed research scheduler and explicit paper onboarding added to fake PAPER lifecycle and local
operator controls; all real-money execution disabled.
**Repository:** private https://github.com/Nkreddy15/signal-vault.
**IMPORTANT CONCURRENT MAIN UPDATE:** During this session `main` changed to
`d960ab81c24c774b88065a31a24b7b52e3becc8e` from a separate source
path, replacing/removing many Phase 2-D components while introducing a
credential boundary and recovery-only supervisor. This session's independent
Phase 2-E source has been preserved on the separate GitHub branch
`dev/phase2e-source-preservation-20260928`, complete-source commit
`174daabb31bb65b63d0e8167cae15c9f692313b9`, exact original source
tree `b0a49b5800b490a6750d05a86ebb38724ad7b490`. Never force push or
overwrite `main`. Phase 2-F ports the independent credential/recovery ideas
into the preservation branch and requires exact new-tree verification before
an additional branch update. Keep this preservation branch as the source of
truth for THIS development track until an explicit integration review.
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
- Phase 2-F: a redacted, sandbox-variable-only paper credential object;
  generic/live credential names are rejected. A GET-only paper recovery
  supervisor shares the source reader's exact credentials with the executor,
  resolves UNKNOWN by client ID, polls known orders and may independently audit
  terminal cash/position/order evidence without sending new orders. Other
  source edits found on concurrent `main` have NOT been blindly merged.
- `make test`: **130/130 offline tests PASS** at this checkpoint, `make demo`
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

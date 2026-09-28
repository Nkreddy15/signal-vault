# Signal Vault recovery and next work (after Phase 2-F)

1. IMPORTANT: `main` advanced independently to commit `d960ab81` and
   contains overlapping implementation decisions. This development track is
   preserved on `dev/phase2e-source-preservation-20260928` as an exact tree;
   Phase 2-F must be fast-forwarded ONLY on that branch, never on main. Read
   this branch's `PROJECT_STATUS.md`, `ARCHITECTURE.md`, `NEXT_STEPS.md`; use
   the Library Phase2F ZIP as fallback. Do not force push or overwrite main.
   Inspect/compare the two branches and merge specific improvements through a
   reviewed integration workflow, avoiding deletion of safety features.
2. Run `make smoke` (130/130 tests at this point). It includes offline unit tests, a deliberately fake paper
   broker lifecycle and Python source compilation. Verify live mode remains
   permanently rejected. Do not mistake simulation for provider paper fills.
3. Wire `paper_store` into a single source-backed proposal method that uses
   ONLY its independently reconciled virtual $100 ledger. Persist true
   strict fair USD/BTC fee/spread budgets. Mark-to-market peak and UTC-day
   baselines are now durably tracked; retain and extend the tests. Never trust the caller to manufacture a $100 PortfolioSnapshot.
   Integrate the new source asset minimum/step and dust-aware exit preview;
   the dust operating mandate still needs explicit owner confirmation.
4. The uninvoked, mock-tested `paper_onboarding` GET-only code exists; run
   a genuine paper-account API compatibility smoke test **only after separate
   authorization and secure paper credentials outside this chat**. Verify trading eligibility, account
   status, BTC/USD metadata, quote/asset mapping, fee calculations and cash
   with real GETs before activating any provider paper POST.
5. The independently tested read-only `PaperRecoverySupervisor` now safely
   checks status and terminal evidence on restarts using matching paper
   credentials. Promote the currently UNARMED read-only research scheduler to
   an independently authorized PAPER-only broker orchestration after onboarding:
   retain staleness guard, exactly-once bar processing, persisted operator
   HALT, interrupt-safe submission, UNKNOWN
   lookup, terminal audit, full fill/fee ledger and restart recovery. Implement
   fault injection, single-writer isolation and structured event alerts.
6. Upgrade local-only dashboard to a private authenticated owner interface;
   cloud hosting needs separately authorized infrastructure and no secrets in
   GitHub or ChatGPT. Maintain immutable paper-only code path. Production
   PostgreSQL and secure deployment are pending.
7. Only after passing fault tests should an authenticated Alpaca PAPER account
   enter a 7-day continuous run. A $100 live pilot on Nov 1 remains a
   conditional target requiring the owner's *new explicit approval*, not an
   automatic toggle or a promise of returns.

**Resumption prompt:** `Continue Signal Vault from the latest private GitHub
checkpoint. Read PROJECT_STATUS.md and NEXT_STEPS.md, run make smoke, continue
paper-only engineering. No external spending, account access or live orders.`

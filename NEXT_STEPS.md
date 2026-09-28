# Signal Vault recovery and next work (after Phase 2-D)

1. Open the private `Nkreddy15/signal-vault` `main` branch and read
   `PROJECT_STATUS.md`, `ARCHITECTURE.md` and this file. Confirm latest branch
   commit and compare against the Library ZIP if there is any source handoff
   issue. Never force-push or overwrite another session's changes.
2. Run `make smoke`. It includes offline unit tests, a deliberately fake paper
   broker lifecycle and Python source compilation. Verify live mode remains
   permanently rejected. Do not mistake simulation for provider paper fills.
3. Implement isolated virtual $100 cash/BTC derivation for all production paper
   proposals, record mark-to-market peak/day baselines, reserve sellable BTC,
   enforce fee/spread budgets and convert Guardian to a durable preflight
   using provider-backed snapshots rather than caller-supplied PortfolioSnapshot.
4. Implement actual read-only paper-account onboarding and a provider API
   compatibility smoke test **only after separate authorization and secure
   paper credentials outside this chat**. Verify trading eligibility, account
   status, BTC/USD metadata, quote/asset mapping, fee calculations and cash
   with real GETs before activating any provider paper POST.
5. Paper-only autonomous scheduler: data staleness guard, exactly-once bar
   processing, persisted operator HALT, interrupt-safe submission, UNKNOWN
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

# October 2026 milestone plan (target: November 1 conditional pilot)

- **Sept 28–30**: Phase 1 architecture, offline kernel, tests, secure repository remote, freeze paper-only requirements.
- **Oct 1–4**: broker contract refinement, market feed normalization, asset rule validation, strategy/backtest harness.
- **Oct 5–9**: Alpaca paper adapter, idempotent order ledger, quote guard, deterministic signal runner.
- **Oct 10–14**: dashboard, durable scheduler, failure recovery, fault injection, paper-only deployment.
- **Oct 15–21**: seven uninterrupted days of genuine autonomous paper operation (not the offline dry run); $100 logical budget.
- **Oct 22–27**: audit trades, correct discrepancies, estimate fees/slippage, extend test if critical issues are found.
- **Oct 28–31**: independent safety review, health checks, owner walkthrough; live execution remains disabled.
- **Nov 1**: *conditional* decision on whether even a limited $100 live pilot merits a separately engineered/authorized live release. Never automatic.

Time estimates are aggressive and require access, successful integrations and enough development sessions under ChatGPT Plus usage limits. No work occurs autonomously between chat/Work sessions. The eventual independently deployed paper application can run continuously once it has actually been built and deployed.

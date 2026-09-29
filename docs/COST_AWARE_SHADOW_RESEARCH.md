# Phase 3: Cost-aware shadow research — NO trading orders

This module is the **research-gate foundation**, not a replacement for strategy validation. The initial EMA v0.1, confirmed v0.2, and momentum v0.3 candidates have not yet demonstrated satisfactory prospective after-cost returns. One real, separately approved $15 PAPER **diagnostic** buy was successfully broker-reconciled September 29, 2026, but its final crypto fee remained deferred. That isolated broker integration test was **not** a strategy-generated BUY, a SELL, an automated trade, or proof of edge.

The existing owner-installed Mac `:07` LaunchAgent now has a verified first distinct automatic prospective observation: `ONE_NEW_PROSPECTIVE_CANDLE_RECORDED` at 2026-09-29T19:07:00Z, archived count 1. This is an **owner-reported** sanitized local receipt; this GitHub change does not access the owner's local files. No collector reinstall, reinitialization, change or manual hourly attendance is needed.

## The new offline cost gate

`src/signal_vault/shadow_cost_gate.py` is pure Decimal research code, with a read-only optional CLI. It never imports a broker order executor, accesses credentials/network, creates/upgrades a journal, issues a signal trade or modifies the LaunchAgent.

Initial, explicitly labelled **research assumptions**:
- $15 illustrative buy, the same scale as the approved diagnostic PAPER buy.
- Alpaca tier-one taker fee budget: **25 bps per leg** as documented at [Alpaca Crypto Spot Trading Fees](https://docs.alpaca.markets/us/docs/crypto-trading). This is an assumption; verify actual tier/fees when trading is separately authorized. Crypto BUY fee can consume received base asset; SELL fees reduce USD proceeds.
- Slippage stress allowance: **10 bps on each leg** (hypothesis, not measured execution).
- Spread input: **3 bps hypothetical for both legs by default**. It is NOT today's quote. The owner can supply a different scenario.
- Required net margin buffer **20 bps** beyond recouping modeled execution costs; it is a predeclared research hurdle, not evidence of predicted returns.

Mathematics normalizes the entry midprice to 1, charges entry at `ask * (1 + entry_slippage)`, subtracts the BTC-denominated buy fee from received quantity, models exit at future `bid * (1 - exit_slippage)`, and subtracts the sell fee from resulting USD. The break-even and net-target gross future midprice rise are solved algebraically, not equated to fee percentage alone. It models BOTH half-spread crossings for flat-market round trips. Exit spreads, actual broker fees, slippage and order fills can be worse.

`review_shadow_signal` remains fail closed: a deterministic EMA **BUY** crossover is directional evidence only. With no independent prospective return calibration (the current state) it produces `BUY_VETO_NO_INDEPENDENT_PROSPECTIVE_EDGE_EVIDENCE`, even when price is rising or someone supplies an arbitrarily large unvalidated forecast. A tested hypothetical estimate exceeding the hurdle can become only `RESEARCH_ONLY_BUY_CANDIDATE_PASSES_COST_ASSUMPTIONS`; the module **always** says strategy not promoted, broker-order submission disabled. HOLD stays HOLD. A risk-reducing SELL candidate is never blocked just because its sale might realize a loss; it still requires actual position/Guardian/permission checks outside this research module.

## Owner-optional offline report

After pulling the merged change:

```sh
PYTHONPATH=src python -m signal_vault.shadow_cost_gate
```

This invokes existing `status_unattended` **offline**, using its independently audited local archive and latest sanitized receipt. It prints the verified automatic prospective-observation count (currently owner-reported as one), plus the **assumed, not live** round-trip economics. It does not capture market data, look at a paper account, retrieve keys, request a quote or post orders. For a hypothetical spread stress test only:

```sh
PYTHONPATH=src python -m signal_vault.shadow_cost_gate --assumed-spread-bps 15
```

`168` completed consecutive prospective hourly bars is an **initial sample inspection checkpoint**, not a credible minimum proof of profit or an automatic promotion threshold. Multi-fold disjoint evaluation, sufficient actual BUY and SELL opportunities, out-of-sample after-fee net returns, drawdown, reproducible source evidence, delayed fee validation, and separate approval all remain prerequisites for a strategy release. A single prospective bar alone supports only collection integrity, not strategy performance.

The same PR corrects the older `phase3_readiness` wording: it now reports `SUPERVISED_PAPER_ORDER_RESULT_NOT_TRACKED_BY_OFFLINE_REPORT` rather than falsely implying that an authorized supervised broker test never occurred. The offline reporter deliberately cannot attest independent broker operations simply by rereading archival collector and ledger status.

**No second PAPER order or SELL is authorized.** The $15 diagnostic BUY remains a separate currently reconciled account position, with the provider fee still pending the owner-approved GET-only finalization. Any future sell or strategy-driven PAPER run requires a new scope/authorization and its own engineering safety checks.

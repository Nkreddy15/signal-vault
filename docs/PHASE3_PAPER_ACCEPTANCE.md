# Phase 3: Paper execution acceptance contract (CODE/PLANNING ONLY)

Date: 2026-09-29. Branch: `phase3-paper-acceptance-20260929`. This is a non-executing engineering plan; it does NOT authorize any Alpaca order POST, funding, live trading, paid deployment or change to the installed Mac GET-only LaunchAgent.

## Verified current boundary (owner-reported)

- Existing original manually acquired BTC/USD observation journal: three genuine prospective observations, isolated snapshot and scratch-recovery drill owner-verified. Leave immutable.
- Owner's Mac: `mac_forward_agent --install` reported `launch_agent_loaded:true`, and `--status` reported `plist_exists:true`, `launch_agent_loaded:true`, minute :07 on 2026-09-29.
- BOTH Alpaca PAPER data credentials are accessible in owner's local Keychain. Never print/copy them to source or chat.
- Installed LaunchAgent is strictly market-data GET only and creates a distinct automatic segment. First scheduled tick bootstraps **zero prospective observations**. Following consecutive tick can append one new close. **Neither has yet been evidenced in conversation**.
- Research candidates v0.1, v0.2, v0.3 are NOT promoted (failed after-cost development criteria). No paper broker POST or provider-confirmed paper fill has been evidenced. Default execution must stay disabled.

## Acceptance sequence (do not skip gates)

1. **Collector acceptance, read-only:** owner runs `PYTHONPATH=src python -m signal_vault.unattended_forward_cycle --status` only *after* next actual scheduled :07 tick; first eligible receipt should be `FIRST_AUTO_SEGMENT_BOOTSTRAPPED` and count 0. Following consecutive eligible tick should be `ONE_NEW_PROSPECTIVE_CANDLE_RECORDED` and count 1. Check sanitized operational receipt, full chain audit, date and freshness. If missed cycle, accept distinct new segment, never retroactive backfill. Keep independent owner manual journal/snapshot untouched.
2. **Read-only broker/account preflight:** separate PAPER-trading account permission checks; symbol tradability and min/step constraints; available paper buying power; time/source freshness; provider product-specific fees/slippage; strict paper host allowlist; do not treat GET data Keychain access as authority to execute POST.
3. **Paper-order adapter contract (tests with fake transports first):** approved immutable draft, durable SUBMISSION_PENDING preceding POST; deterministic client order ID; exactly once local attempt; response-state parsing; timeout -> UNKNOWN_RESULT, query/reconcile before any further order; reject stale quotes, wrong market, invalid decimals, redirects or unexpected hosts.
4. **Operator-only supervised smoke (separate explicit approval needed):** a tiny bounded BTC/USD PAPER order with hardcoded PAPER host, reviewed ID/size/risk limits, no live fallback. Verify actual provider order ID and final fill status; log observed fills, fees and position, not assumed fills. No automatically repeating submission during this milestone. If error, operator HALT and inspect safe receipt.
5. **Shadow signals independent of execution:** new candidate must be preregistered, measured out of sample/prospectively and account for realistic spread/fees. A completed broker smoke does not qualify a strategy for autonomous orders. HOLD must always be valid.
6. **Multi-market expansion as independent contracts:** BTC/USD first; ETH/USD and SOL/USD require distinct instrument/fee/step/provider validation, individual strategy evidence and market-specific limits. Future equity adapter must account for market hours/order restrictions; never treat stocks as BTC with another ticker.
7. **Seven-day monitored PAPER operations before any broader paper autonomy:** verify missed cycle recovery, process restarts, UNKNOWN_RESULT, duplicate prevention, reconciliation, drawdown halt, daily summaries and immutable evidence. Any provider drift -> fail closed. Actual live money requires a later separate release and explicit authorization.

## Immediate next local, non-trading check

```sh
PYTHONPATH=src python -m signal_vault.unattended_forward_cycle --status
```

This reads only sanitized local operator state; it does NOT run a market capture or order. A LaunchAgent reported loaded is **not** evidence of real collection, and three original manual observations must not be counted as automatic observations.

## Work implementation split

- Engineering task A: isolate PAPER-trading credential/permission gate from existing DATA GET-only Keychain services; no trading key read by the unattended observer.
- Task B: offline broker preflight with fake-provider fault injection and printable secret-free PASS/BLOCKED receipts.
- Task C: supervised single-order command, **disabled by default**, with exact acknowledgement, irreversible pre-POST journal state, provider reconciliation and hard ceiling.
- Task D: independent shadow strategy and multi-asset research adapters.
- Task E: CI tests for forbidden live host, paper POST by GET worker, duplicate submission, unknown results, missing/invalid permissions, bad symbol increments, stale quote and halt override.

**Implementation of an execution command is not authorization to invoke it.** No change to currently running macOS LaunchAgent is requested in this branch.

# Phase 3: First real prospective shadow signal — offline, no trades

The owner's Mac automatic collector recorded the first genuine prospectively
observed, fully closed BTC/USD hourly candle, evidenced by the owner-reported
`ONE_NEW_PROSPECTIVE_CANDLE_RECORDED`, `prospective_observations_verified: 1`
at 2026-09-29T19:07Z. The bootstrap history is not counted as prospective.
The first real $15 Alpaca PAPER diagnostic BUY was separately authorized,
broker-accepted and independently reconciled; **that buy was not selected by
the strategy, and no sell was submitted**. Its eventual provider crypto fee
activity is still pending. The Mac collector requires no hourly attendance.

## Latest archived shadow signal report

After pulling the reviewed merge, **optional offline diagnostic only**:

```sh
PYTHONPATH=src python -m signal_vault.shadow_signal_snapshot
```

This new standalone command:

1. Calls the existing `status_unattended` which audits the entire current
   automatic journal, original anchor, each captured CSV/manifest SHA and
   hourly prospective time boundary. It refuses bootstrap-only and HALT.
2. Opens the reported, validated, fixed-name automatic segment in SQLite
   `mode=ro` and `PRAGMA query_only=ON`. Reads the **latest** prospective
   observation's precise UTC start, close, observation timestamp and captured
   CSV hash.
3. Re-reads only the exact named 72-hour archived capture, checks 0600 file
   permissions, the expected saved SHA-256, the manifest SHA/source/bounds,
   and the latest observed candle's UTC time. Rechecks the independent
   archive status after the read, refusing a changed segment, count or end.
4. On this **one most-recent genuinely prospective closing candle** evaluates
   unchanged deterministic EMA v0.1 and independently named research-only
   v0.2 (second bar confirmation) and v0.3 (50-bps prior 24h return) signals.
   The 72-hour history is permitted for indicator warmup but is never
   labelled 72 prospective observations.
5. Uses `shadow_cost_gate`'s explicit **hypothetical** spread and assumed
   two-sided fee/slippage model. No actual future return prediction has been
   prospectively validated. An EMA BUY crossover consequently remains a
   **research HOLD** under the economic gate. A SELL crossover is only a
   risk-review candidate (not an instruction to sell the owner-held BTC).
   Neutral signals stay HOLD. Every result marks actual order submission
   disabled and strategy not promoted.

The result includes the archived observation timestamp, capture SHA,
historical close (NOT a live quote), evidence ID, fast/slow EMA values,
research direction and reason. It makes **no broker or market-data request**,
accesses no paper account, credentials or Keychain, writes nothing, and does
not call any trading worker or modify the owner's hourly Mac LaunchAgent.

Alternative cost sensitivity scenario, **not a measured live spread**:

```sh
PYTHONPATH=src python -m signal_vault.shadow_signal_snapshot --assumed-spread-bps 15
```

Unchanged offline cost-gate findings at the default assumed 3 bps spread:
`73.34` bps round-trip break-even BTC midprice appreciation,
`93.48` bps gross appreciation to the predeclared 20-bps net research
margin, illustrative flat-mid $15 loss `$0.1092`. Inputs: 25bps taker fee
per side and hypothetical 10bps slippage allowance per side. These are
simulation economics, NOT actual trading returns, current spreads or
independently validated future forecasts. Larger starting capital does
not solve poor percentage economics.

A minimum of 168 contiguous prospective hourly observations is only an
initial review checkpoint; it is not automatic evidence of profitability or
strategy promotion. Real after-cost OOS evaluation and trade-specific
approval remain necessary. No further PAPER BUY/SELL is authorized by this
module. Keep the diagnostic BTC position and the hourly collector unchanged.

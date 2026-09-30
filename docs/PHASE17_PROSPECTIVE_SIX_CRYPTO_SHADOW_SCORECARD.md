# Phase 17 — Prospective six-crypto shadow scorecard

The deployed six-crypto sidecar archives a fixed four-hypothesis shadow only
**after** a genuinely new prospective source hour has been observed. That
shadow is for the next bar. It is therefore possible to evaluate strategy
behavior later without pretending a retrospective backtest was a forward test.

`six_crypto_forward_scorecard.py` is offline and read-only. It never calls
Alpaca, reads credentials, changes Railway evidence, queries broker positions,
or submits an order.

## Chronology

Suppose the historical-only 72h bootstrap closes at T0:

- At T0: baseline exists; **0** prospective source hours and **no shadow**.
- At T1: first genuinely observed sidecar hour T0→T1 arrives. Shadow S1 is
  created using only information available at T1 and describes action at the
  next open T1.
- At T2: second genuinely observed hour T1→T2 arrives. S1 now has one fully
  observed outcome. New shadow S2 is created for T2→T3.
- With **N prospective source hours there are only N−1 fully observed
  precommitted shadow outcomes**.

This distinction means the existing 168-hour collector milestone and a
168-decision outcome scorecard are not identical:

- 168 consecutive source hours → six-market source collection milestone.
- 169 consecutive source hours → 168 complete precommitted next-hour
  decision outcomes can be scored.

The latest shadow is always left unscored until its subsequent source hour
exists.

## Evidence validation

Before any simulated P&L is reported, the scorecard:

1. Reaudits the full six-market source receipt chain.
2. Groups receipts by immutable segment; a gap must begin with another 72h
   historical-only baseline.
3. Verifies every persisted shadow file from every preserved segment.
4. Reconstructs each shadow using only that segment prefix that existed at
   the original decision timestamp. Later candles are excluded.
5. Requires exact stored shadow JSON equality, exact source-receipt SHA
   binding, private file permissions, and no unknown extra shadow files.
6. Builds the current segment's six datasets: first 72 hours remain
   historical warmup, later source rows are marked prospectively observed.
7. Restricts all shared-book events to start at the **first precommitted
   shadow time** and end at the latest fully observed close.
8. Checks every synthetic fill's signal SHA against exactly one archived
   pre-outcome BUY/SELL shadow before accepting it in the scorecard.

The scorer runs the existing four fixed hypotheses under the same three
explicit illustrative crypto friction scenarios using one shared
hypothetical $100 bankroll and $30 combined exposure cap. Results include
exit-inclusive P&L, fees, sampled drawdown, fills, open positions and
risk-gate state. Cost assumptions are estimates, not measured executions.

No strategy is selected, ranked, promoted or authorized by this module.
Even 168 forward outcomes remain one short, highly correlated crypto sample.
Automatic PAPER orders stay disabled and LIVE remains unavailable.

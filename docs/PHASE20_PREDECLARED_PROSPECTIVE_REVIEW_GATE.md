# Phase 20 — Prospective forward review gate frozen before scored outcomes

The six-crypto sidecar's first real production tick at 2026-09-30 03:08:20Z
created only its 72-hour retrospective baseline and therefore **zero**
prospective sidecar hours. No prospective six-market strategy outcome had been
scored when this Phase 20 policy was written.

This is the correct point to freeze review criteria: before future results can
tempt us to move thresholds after seeing them.

## Policy v1

`six-crypto-forward-review-gate-v1-predeclared-20260930`

Only the two active fixed research hypotheses are assessed:

- `generic-ema12x26-v1-predeclared`
- `generic-momentum24bar50bps-v1-predeclared`

Cash and the one-allocation passive hypothesis remain permanent comparators
and can never be promoted by this gate.

An active candidate can meet the frozen **owner PAPER execution design
review** criteria only if all of the following are true:

1. At least **169 consecutive prospective six-crypto source hours** exist in
   the current segment.
2. Therefore at least **168 fully observed precommitted next-hour shadow
   outcomes** exist.
3. At least **10 synthetic fills** occurred in the base-friction forward
   replay, reusing the older research-gate minimum-fill principle.
4. Exit-inclusive P&L is positive under **base** illustrative friction.
5. Exit-inclusive P&L is positive under **high** illustrative friction.
6. It outperforms the same shared-book passive comparator under base friction.
7. It outperforms the same shared-book passive comparator under high friction.
8. Base sampled event drawdown is at or below the existing **$10** logical
   research-account review limit.
9. High-friction sampled event drawdown is at or below $10.
10. Neither base nor high-friction replay trips the persistent peak-drawdown
    entry halt.

The v1 dataclass refuses in-place threshold edits. A future threshold change
must use a new policy version and a new future evaluation sample; it must not
rewrite this policy after observing Phase 20 outcomes.

## What passing means — and what it does not

Passing means only: **eligible for a separate owner-authorized PAPER execution
design review**.

It does NOT:

- select or rank a candidate;
- establish future profitability;
- authorize Alpaca PAPER order POST;
- read broker positions or balances;
- enable automatic trading;
- enable LIVE trading;
- override venue/minimum/fee/account eligibility checks;
- allow the existing sidecar collector to submit an order.

Even if both active candidates meet every criterion, the report returns both
without preference and keeps automatic candidate selection disabled.

The CLI can read a saved Phase 17 scorecard JSON and print the frozen gate
assessment:

```sh
PYTHONPATH=src python -m signal_vault.six_crypto_forward_review_gate \
  --scorecard /private/path/prospective_scorecard.json
```

It is read-only and bounded; malformed/symlinked/oversized input fails closed.

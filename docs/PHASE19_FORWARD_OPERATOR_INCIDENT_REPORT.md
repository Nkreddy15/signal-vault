# Phase 19 — Read-only forward operator/incident report

The production collector now has two evidence streams and multiple independent
offline validators. Phase 19 provides one conservative summary without giving
the summary tool any power to repair or mutate the collector.

`forward_operator_report.py` composes:

- Phase 16 BTC/six-crypto cross-stream integrity and clock alignment;
- Phase 18 storage/reserve/capacity audit; and
- Phase 17 prospective immutable-shadow scorecard.

It never requests market data, reads credential values, calls Railway,
writes/repairs a journal, clears a pause, backfills a missing hour, deletes
evidence, purchases resources, or submits PAPER/LIVE orders.

The report emits one severity:

- **INFO** — valid early-stage or aligned evidence; continue/wait for the
  already scheduled collector.
- **WARNING** — valid evidence but sidecar lag or capacity projection deserves
  attention if it persists.
- **HALT_REVIEW** — BTC durable pause, integrity/source-shadow failure, or a
  hard storage guard would prevent the next sidecar tick.

Even HALT_REVIEW is deliberately non-automatic. It means preserve all evidence
and inspect. The report explicitly forbids automatic evidence deletion,
backfill, durable-pause clearing, credential changes, paid-resource creation,
PAPER order activation and LIVE trading.

The report keeps the two validation milestones separate:

- 168 consecutive current-segment six-crypto **source hours**;
- 168 fully observed precommitted shadow outcomes, requiring at least
  169 prospective source hours.

Neither milestone itself proves profitable edge or authorizes trading.

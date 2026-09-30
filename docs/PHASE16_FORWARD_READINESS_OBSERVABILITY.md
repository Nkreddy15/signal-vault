# Phase 16 — Forward observability, shadow recovery and two readiness milestones

The owner-approved BTC-FIRST six-crypto Railway production activation first
ran at 2026-09-30T03:08Z. The existing BTC collector remained healthy and
reported its seventh consecutive prospective BTC observation. The six-market
sidecar created its exact 72-hour historical warmup at the same tick and
correctly counted **ZERO** prospective six-market hours.

This phase does not add provider calls, trading, new resources or credentials.
It makes the existing evidence chain easier to audit without touching it.

## Read-only dual status

`python -m signal_vault.railway_btc_first_dual_cron --status`

is credential-free and makes **ZERO network requests**. It re-audits:
- original BTC cloud evidence through the pre-existing `cloud_status`;
- every six-market source receipt and SHA link;
- every current/old deterministic shadow file against the exact source chain
  that existed when that shadow was first precommitted;
- current contiguous six-market segment count and latest observed UTC close;
- latest source/shadow parity.

The active `--once` runtime also reports cumulative current-segment source
hours after every sidecar source commit, rather than just “one hour this
tick”.

## Crash-safe derived-shadow recovery

Source receipts are the immutable first-class observations. A process could
crash after committing one new six-market source receipt but before writing
its derived offline shadow. Previously a later hour could leave that older
derived file missing indefinitely.

`repair_six_crypto_shadow_archive` is keyless and deterministic. It:
1. verifies the entire immutable source chain first;
2. reconstructs each historical pre-outcome shadow using only the prefix that
   existed at that receipt's original time;
3. never uses future source rows when reconstructing an older shadow;
4. creates only a missing exact 0600 shadow file with O_EXCL;
5. refuses mismatched/tampered/extraneous files instead of overwriting them;
6. performs no provider request and never changes source receipts.

The existing `archive_six_crypto_shadow` remains backward-compatible but
now invokes this full recovery path, so a normal later tick or safe duplicate
can repair prior derived-shadow write interruptions without downloading bars
again.

## Two different milestones — do not collapse them

**Source collection milestone:** 168 consecutive genuinely prospective UTC
hours in the current six-market segment. That is 168 independent clock hours
and 1008 asset-bars. The 72h historical baseline is not counted.

**Fully scored precommitted-outcome milestone:** 168 decisions whose *next
hour outcome* has subsequently arrived. The first prospective source hour can
only precommit a decision for the following hour, so 168 fully observed
precommitted intervals require **169 prospective source hours**.

Therefore:
- at 168 source hours, `sidecar_source_168_hour_collection_ready=true`;
- the full scorecard is still one outcome short;
- at 169 source hours (if no gaps), 168 precommitted intervals can be scored.

Any missed scheduled source hour starts a new zero-prospective segment. Old
evidence remains immutable but does not substitute for the new segment's
consecutive clock time.

## Production safety remains unchanged

- BTC runs before the six-market sidecar.
- No source receipt, shadow or readiness calculation submits an order.
- Automatic PAPER trading: DISABLED.
- LIVE trading: UNAVAILABLE.
- No account positions are queried for the six-market shadow.
- The shared 500 MB volume remains protected by the 128 MiB BTC free-space
  reserve and 32 MiB sidecar hard cap; evidence is never automatically
  pruned to make a metric look ready.

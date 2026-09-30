# Phase 18 — Sidecar storage and retention audit

The active Railway BTC-first collector shares one 500 MB persistent volume.
The six-crypto sidecar is deliberately bounded so that preserving the
original BTC evidence always has priority over collecting another sidecar
hour.

`six_crypto_storage_audit.py` is a read-only capacity auditor. It does not
create, prune, compact, migrate, upload, delete, or rewrite any evidence.

It reports the exact sidecar byte footprint and file count, current
filesystem free bytes, bytes above the reserved BTC floor, the hard sidecar
cap, and whether the same hard conditions enforced by the runtime collector
would permit one more sidecar tick:

- reserve at least **128 MiB** of free filesystem space for BTC;
- sidecar immutable evidence hard cap **32 MiB**;
- reserve up to **4 MiB** for the next individual sidecar tick.

The sidecar collector itself already fails closed rather than deleting data
when these limits are approached. Phase 18 adds visibility only.

After the first genuinely prospective sidecar hour has both its immutable
source receipt and immutable shadow, the auditor measures actual pair sizes.
It then gives a descriptive conservative projection using the **largest
observed receipt+shadow pair so far** for the remaining hours to:

- 168 consecutive prospective source hours; and
- 169 source hours, which are needed for 168 fully observed precommitted
  decision outcomes in the Phase 17 scorecard.

The projection is explicitly not a guarantee. Provider payload size,
additional source fields, future shadow representation, and unrelated BTC
disk growth could change later usage. Each future runtime tick still applies
the hard reserve/cap checks independently.

A warning never authorizes deletion. Automatic pruning is DISABLED and
original BTC files may **never** be removed to make room for six-market
research. If the hard guard would reject another sidecar tick, preserve all
evidence and investigate capacity before making any infrastructure decision.

The module performs no provider request, accesses no credential value,
changes no Railway resource, and submits no order.

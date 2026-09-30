# Phase 16 — Read-only BTC + six-crypto cross-stream integrity status

This phase is deliberately **offline** and cannot change the live Railway
collector. It exists because a healthy BTC-first deployment now has two
different evidence streams on the same physical volume:

- the original BTC prospective SQLite/capture/shadow chain; and
- the isolated six-crypto JSON receipt/shadow chain.

The two streams must never be conflated. BTC started accumulating genuine
prospective observations earlier. The six-crypto stream begins with a 72-hour
retrospective baseline that counts **zero** prospective hours.

`src/signal_vault/dual_forward_integrity.py` calls only existing strict
read-only auditors. It does not load credentials, call Alpaca, create a
sidecar, alter file permissions, clear a pause, append observations, create
orders, or recover/repair any evidence.

It reports:

- current verified BTC prospective count and latest closed hour;
- whether the six-crypto private namespace exists yet;
- current six-crypto segment index and baseline count;
- six-crypto genuinely prospective clock hours;
- six-crypto prospective asset-bar count, enforcing exactly
  `6 asset bars = 1 independent UTC clock hour`;
- exact whole-hour lag of the six-crypto stream behind the BTC-first stream;
- source/shadow prospective-count equality;
- whether the current **contiguous** sidecar segment has reached 168
  prospective UTC hours.

A sidecar timestamp later than the BTC-first stream fails closed. A missing
latest shadow cannot be described as current signal evidence. A one-hour lag
is reported as a warning rather than silently relabeled aligned. A BTC durable
pause preserves and reports all sidecar evidence but never claims overall
health.

The first sidecar baseline should therefore read:

`BTC_HEALTHY_SIX_CRYPTO_BASELINE_ONLY`

with zero prospective hours, even though it contains 72 historical hourly
source bars for each of six symbols.

After the next exactly contiguous successful scheduled tick the intended
state is:

`BTC_AND_SIX_CRYPTO_CURRENTLY_ALIGNED`

with **1 independent prospective hour / 6 prospective asset-bars** plus a
matching immutable six-market shadow.

At 168 consecutive current-segment sidecar hours the status may say
`SIX_CRYPTO_168_HOUR_CONTIGUOUS_EVIDENCE_READY`. That means only the
preregistered forward evidence window exists. It is **not** a finding of
profitability, strategy promotion, statistical independence of six assets,
or permission for PAPER/LIVE order submission.

This module is intentionally not in the production Railway watch-path list
during the initial activation verification. Merging Phase 16 therefore does
not rebuild or restart the new BTC-first production image. It can be added to
a future operational image after the first real sidecar baseline and first
prospective hour have been independently verified from Railway runtime logs.

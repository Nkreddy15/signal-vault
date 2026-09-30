# Phase 15 — Free-tier-compatible BTC-FIRST six-crypto prospective rollout

## Why the plan changed, without buying anything

Railway's current documentation lists **ONE persistent volume per project on
Free**, default 0.5 GB (the original BTC-only source already owns it).
The Free tier also has plan constraints on Cron jobs after its trial.
Do NOT silently create a second persistent volume, promise a free second
cron or upgrade the owner to a paid tier.

Official: https://docs.railway.com/volumes/reference
and https://railway.com/pricing

The original Railway service remains:
`btcusd-hourly-get-cron` at native UTC `7 * * * *`, with
original 0700 persistent volume at
`/var/lib/signal-vault/forward`. Its BTC-only
`railway_forward_cron.railway_once` has not been edited, replaced or
configured differently by merging this source branch.

`railway_btc_first_dual_cron.py` provides an **unactivated** optional
BTC-FIRST coordinator that uses that SAME existing service, SAME
attached volume, SAME already-authorized purpose-scoped GET-only DATA
variable names, same one hourly Railway scheduler and NO new storage
allocation or billing commitment. It never copies raw BTC existing
journal/manifest/shadow files into six-market storage.

Under owner-approved opt-in, it creates only a new private 0700 logical
namespace:

`/var/lib/signal-vault/forward/isolated-six-crypto-prospective`

This exact pathname alone has been newly allowlisted by the Phase 13
six-crypto `_safe_root` guard. It rejects the original BTC root,
any other nested/source path, symlink alias, insecure parent/root or
attempt to share an individual BTC evidence receipt. Filesystem
isolation is LOGICAL (not independent disk fault tolerance); both
sources still share the same physical 500 MB volume and outage risk.
The all-previous-receipts SHA audit remains mandatory for both streams.

## BTC is always run FIRST, and is never masked by sidecar failure

1. Verify Railway's own `RAILWAY_VOLUME_MOUNT_PATH` matches the expected
   original attached BTC persistent root (same owner-private check as
   original cron).
2. Invoke the existing **unchanged** `railway_forward_cron.railway_once`,
   with its own UTC close checks, segment, shadow, pause and fail-closed
   evidence audit. The six-market sidecar must never precede it.
3. If BTC reports any failure/pause, SKIP sidecar. If new sidecar opt-in
   is unset/unknown, no sidecar folder/provider/network call is created;
   BTC runs exactly as before.
4. Only after BTC success AND the EXACT explicit sidecar flag, verify
   or create the ONE new isolated owner-private subdirectory, then use
   existing purpose-scoped Railway DATA-only keys inside the existing
   bounded 6-symbol GET client, with source values never printed.
5. Phase 13/14 source and shadow work sequentially on a separately
   locked, create-only chain: first 72h-per-symbol retrospective
   bootstrap counts ZERO forward; each subsequent successfully
   collected, contiguous new UTC closed hour adds six genuine
   prospective asset-bars / ONE independent UTC clock hour. The
   keyless shadow computes flat/held hypothetical fixed hypotheses.
6. A missing six-symbol candle, corrupted sidecar folder, provider
   exception or failed shadow is returned separately as
   `sidecar_status`, `sidecar_failure_class` or shadow failure.
   It CANNOT reverse already committed BTC receipts or change the
   original `btc_status`. The CLI's success/fail code continues to
   reflect BTC health; six-market sidecar health must be audited and
   alerted independently using the explicit status fields.

No broker/order endpoint, POST, generic/LIVE/PAPER order key, SIP upgrade,
new account connection, new paid service, new volume or historical
data promotion is introduced by this code. Both source streams are
research-only; BTC and the new six-asset prospective segments are
independent evidence and must NOT be concatenated to artificially hit
the 168-clock-hour validation target.

## Exact future one-time activation (NOT yet performed)

The reviewed `Dockerfile` **STILL** executes the original command:

`python -m signal_vault.railway_forward_cron --once`

When the owner explicitly approves changing the deployed collector,
stage these TWO settings on the EXISTING original BTC service only:

| Setting | Value |
|---|---|
| Start command | `python -m signal_vault.railway_btc_first_dual_cron --once` |
| New non-secret activation flag | `SIGNAL_VAULT_SIX_CRYPTO_SIDECAR=BTC_FIRST_ISOLATED_DATA_GET_ONLY_NO_ORDERS_V1` |

Keep the existing `7 * * * *` UTC cron, source GitHub commit,
`RAILWAY_VOLUME_MOUNT_PATH`, original DATA credential variables,
`RAILWAY_RUN_UID=0`, existing original volume and no public domain
unchanged. DO NOT create the separate volume/service described as
the paid-plan alternative in Phase 13. Do not enable this wrapper on
any other existing/empty Railway service. After staging, review the
change and explicitly deploy once, then require logs to demonstrate
BTC FIRST, independent new six-coin zero-prospective baseline, no
broker submission and unchanged old BTC confirmed count. Subsequent
UTC clock-hour logs should show new six-asset prospective receipts
without a BTC gap.

**Trade-off:** a longer six-asset source call increases aggregate cron
duration; old BTC is always attempted first and preserves its
own independence. If the Free plan stops supporting native Cron after
trial, do not claim uninterrupted collection; the already scheduled
external health watch should surface missing prospective ticks.

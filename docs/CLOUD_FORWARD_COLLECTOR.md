# Signal Vault: cloud-READY, isolated GET-only forward collector

**Date:** 2026-09-29. **Status:** preparation and fake-provider CI only.
This GitHub addition does NOT buy a server, activate hosting, copy Mac files,
read the owner's Keychain, provision secrets, place PAPER orders, make a SELL,
or start an autonomous strategy. No recurring ChatGPT task is required for
the collector; a future explicitly deployed container would run its own
in-process UTC :07 scheduler.

## Why this exists

The Mac LaunchAgent has demonstrated its first owner-reported real scheduled
prospective BTC/USD close at 2026-09-29T19:07Z (one observation). Requiring a
personal Mac to stay awake 168 consecutive hours is impractical. The new
*independently provisioned* cloud instance can collect an uninterrupted
research stream if its host stays up and Alpaca data remains accessible.
The earlier Mac/manual records remain on the Mac, never copied, mutated or
counted as newly collected cloud evidence. On its FIRST cloud :07 run, the
collector bootstraps a 72h historical anchor but counts ZERO prospective
observations. On each following consecutive current hour it can append
ONE properly time-stamped, SHA/manifest-verified observation. A genuinely
missed hour starts a distinct new zero-count segment: **never backfill**.

Neither 168 observations nor a profitable-looking historical window proves
a deployable strategy. Research returns must be prospectively out-of-sample
and *after* actual fees, spread and slippage.

## Isolation and non-trading contract

- `src/signal_vault/cloud_forward_service.py` imports only the fixed Alpaca
  authenticated BTC/USD historical DATA GET adapter
  (`_read_data_get_no_redirect`). The historical-data HTTPS hostname/path,
  allowed query, request method `GET`, redirect refusal, response limits and
  unmodified provider history all come from the already tested local capture.
  It contains no PAPER account, order, POST or live endpoint import.
- **DATA secrets** are loaded from two fixed in-container file mounts:
  `/run/secrets/forward_data_key_id` and
  `/run/secrets/forward_data_secret`. Their values never appear in
  source, image layers, argv, host environment variables or report JSON.
  The service rejects symlink, absent, oversized, malformed or writable-by-
  group/other secret files and any generic/LIVE/order-enabling key environment
  variables. It reads secrets only when the existing exact-hour and prior
  archived-evidence checks permit a new historical DATA GET. An Alpaca PAPER
  API key may itself carry more provider permissions than this application
  exercises: use a *separate PAPER-only credential pair* and a trusted host.
  Application-level GET-only behavior is NOT equivalent to provider-scoped
  read-only credentials or protection against a compromised host.
- Data root `/var/lib/signal-vault/forward` must be an existing 0700
  nonsymlink, writable, **persistent** volume. It never mounts the Mac's
  original `data/forward` or trading ledger. Cloud results/receipts remain
  private 0600 files.
- `ops/cloud/Dockerfile` builds only Python+source using an unprivileged
  numeric UID/GID 10001. The Compose template uses a read-only root
  filesystem, persistent named evidence volume, file-mounted DATA secrets,
  dropped capabilities, no-new-privileges, a small tmpfs, and **no exposed
  ports**, host network, broker account API or Docker socket.
  `.dockerignore` excludes `.git`, owner `data/`, secrets, venv, logs,
  local credentials and archived research files from the build context.
- The long-lived `--serve` container targets each actual UTC hour at :07.
  Starting between minute :07 and :24 is eligible for the current hour;
  later startups skip to the following hour. An in-process last-hour guard,
  existing worker lock, strict immutable capture filenames and the journal's
  idempotent audit prevent duplicate observation/rewriting.
- Each new genuinely prospective bar triggers **offline** evaluation of
  v0.1, v0.2 and v0.3 EMA research signals with the prior documented
  hypothetical cost gate. It writes a deterministic, unique,
  SHA-bound `cloud-shadow-receipts/shadow-YYYYMMDDTHHMMZ.json`. The same
  exact receipt may be revalidated idempotently, but a collision or
  altered one is refused, NEVER overwritten. First zero-count bootstrap
  cannot manufacture 72 shadow signals.
- On any integrity/capture/shadow failure, the original raw captures and
  journals are retained. A durable
  `.cloud-collector-paused.json` is created and the service parks without
  further scheduled GETs, including after a container restart. Even
  network/Keychain-secret-file errors fail closed rather than risk corrupt
  partially written evidence. This conservative behavior can require a
  separate recovery review; do not delete/rewrite original evidence to
  conceal a HALT.
- No strategy is promoted and there is no automatic paper/live trading.
  An observed SELL directional signal is only research, not authorization
  to close the owner's separately purchased $15 PAPER BTC position.

## What is already safe to use locally

The existing owner's Mac collector and paper journal are entirely independent
of this deployment template. Leave them unchanged. The following code check
does NOT activate a cloud service or place an order:

```sh
python -m unittest discover -s tests -v
```

The fake-provider tests exercise first cloud bootstrap 0, successive
automatic observations 1 and 2 with immutable SHA-bound shadow receipts,
duplicate tick, skipped hour/new segment, bad capture/pause, unchanged
original archive, file-mounted secret permission rejection, forbidden LIVE/
paper-order environment fallbacks and UTC schedule boundaries.
GitHub Actions tests the suite using Python 3.11 and 3.12.
No real cloud API, external network, money or broker POST is used in CI.

## LATER operator-only activation checklist (NOT performed by this PR)

**Preconditions:** approve a specific trustworthy always-on host and its
potential charges, arrange a persistent disk and backup plan, review the
security of a separate PAPER DATA key, and explicitly authorize remote
secret provisioning. Do NOT paste either credential in ChatGPT/GitHub or
bake it into a Docker image. An example Docker Compose blueprint lives in
`ops/cloud/compose.yaml`, but no server/provider is chosen yet.

Only from that explicitly approved, private Linux host with Docker Compose:

1. Clone/pull the reviewed private repo; keep permissions tight. Create
   the host's ignored `secrets/` directory with 0700 permissions. Privately
   provision `secrets/cloud_forward_key_id` and
   `secrets/cloud_forward_secret` using a protected secret manager or
   a masked interactive local host terminal. Use PAPER DATA keys only,
   with no newline/trailing whitespace in either value. Host source
   permissions should be 0600. **Do not copy keys from Mac to chat.**
2. Review the Compose file and Dockerfile, including host volume location,
   isolation and Docker's handling of file-backed secret mount permissions.
   The in-container service UID 10001 must be able to read mounted secrets.
   Check with the below *no-network* preflight, rather than loosening host
   secret permissions or proceeding despite a failure. Provider/VPS secrets
   support differs; adapt secret mounting deliberately if necessary.
3. Run the one-time *nonactivating* validation, from the repository root:

```sh
docker compose -f ops/cloud/compose.yaml build observer
docker compose -f ops/cloud/compose.yaml run --rm --no-deps observer --preflight
```

The expected result is `LOCAL_CLOUD_PREFLIGHT_PASSED_NO_DEPLOYMENT` with
`network_requests: NONE`. The preflight may create the EMPTY named Docker
volume as part of Compose mounting, but it does not start the `--serve`
scheduler, contact Alpaca or write a prospective observation.
An unreadable or missing secret must block activation; never check credentials
into source or expose them through shell command arguments.

4. Only after independent deployment/cost approval, activate:

```sh
docker compose -f ops/cloud/compose.yaml up -d observer
docker compose -f ops/cloud/compose.yaml logs --tail=30 observer
```

The initial eligible UTC HH:07 cloud tick reports
`HISTORY_BOOTSTRAPPED_NO_RETROSPECTIVE_SHADOW` and observation count 0.
Only a following consecutive eligible tick can report
`ONE_PROSPECTIVE_OBSERVATION_AND_SHADOW_ARCHIVED`.
The separate cloud/volume source is never combined with the prior Mac segment
to inflate the count.

5. Safe status, no network/keys/orders:

```sh
docker compose -f ops/cloud/compose.yaml run --rm --no-deps observer --status
```

To stop the cloud collector but KEEP all evidence:

```sh
docker compose -f ops/cloud/compose.yaml stop observer
```

**NEVER run `docker compose down -v`: it deletes the named volume containing
your original cloud evidence.** Container restarts and persistent volumes
are not disaster recovery. Establish verified off-host encrypted backups
and a reversible cloud/Mac cutover separately. Do not stop your existing Mac
LaunchAgent until a new cloud segment has actually passed owner-reviewed
cloud collection tests. Old Mac and new cloud observations must always retain
their separate segment/provenance labels.

## Limits

This is a **cloud-ready package, not a deployed URL or a hosted service**.
A cloud account/VM, explicit billing approval, owner-side provisioning of
secrets/volume, provider data verification and cutover are still required.
No current output can establish 168 cloud observations, uninterrupted
hosting, profitable signals, fee finalization, or permission for another
PAPER or real-money order.

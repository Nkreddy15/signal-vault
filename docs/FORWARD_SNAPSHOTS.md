# Phase 2N — isolated owner-local forward evidence snapshot and verification

**Status:** Implemented and fake-data CI-tested. OFF by default. No network, keys,
broker PAPER POST, LIVE endpoints, deposit, daemon, schedule, strategy promotion,
or modification/replacement of the active forward journal.

## Why this exists

A PAPER-ledger backup utility already exists elsewhere in Signal Vault. That
does **not** secure the separate exploratory forward-observation evidence.
This dedicated operator tool takes a logically consistent SQLite backup
using SQLite's online backup API and copies *only* the original locally retained
72-hour CSV/manifest pairs actually referenced by the copied journal: one
bootstrap pair and one additional pair per observed new UTC hour. Extra unlinked
exploratory captures stay in their original local folder, but are not falsely
claimed as part of the copied journal's evidence chain.

Source validation first uses the separate read-only
`forward_evidence_audit`: any known missing original CSV, altered manifest,
incorrect saved metric, changed candle, failed SQLite integrity, excessive file
permissions or divergent timestamps aborts before publishing a snapshot.
The archive is staged privately, each copy is an independent disk file (not a
hardlink), and a second isolated full forensic audit is run on the copied
journal and its own copied CSVs/manifests BEFORE a completed private directory
is made available. Captures remain immutable in normal collection; the
snapshot's own unsigned manifest records SHA-256 for the copied SQLite and
every referenced source/manifest. It will not knowingly replace an existing
named snapshot. The tool also rejects symlinks and unknown or missing items
on later verification.

## Owner commands, only after source audit succeeds

From the Mac's checked-out repository, with local `.venv` active:

```sh
# 1: No credentials, network or writes. Must pass BEFORE any snapshot:
PYTHONPATH=src python -m signal_vault.forward_evidence_audit

# 2: Explicit manual creation of an independent, owner-only local snapshot:
PYTHONPATH=src python -m signal_vault.forward_snapshot --create

# 3: Use the exact basename reported as "snapshot_path", for example:
#    data/forward/backups/forward_YYYYMMDDTHHMMSS_microsecondsZ
PYTHONPATH=src python -m signal_vault.forward_snapshot --verify <EXACT_SNAPSHOT_FOLDER_BASENAME>
```

`--create` writes only under the ignored `data/forward/backups/` directory,
requires the existing local journal, uses a private 0700 snapshot directory
with owner-only 0600 copied files, and reports counts and path after an
isolated offline verification. The source journal and original captures stay
in their original locations. The tool deliberately has no `--restore` action
and will NEVER copy a snapshot over the active database automatically.

For a separately, explicitly initialized journal segment instead of the
original default `observations.sqlite3`:

```sh
PYTHONPATH=src python -m signal_vault.forward_snapshot --create \
  --db data/forward/observations-segment-02.sqlite3
```

The `--verify` action takes the snapshot **name only**, not an arbitrary
external path. It checks all snapshot file hashes and recomputes the entire
archived observation chain in its isolated folder using SQLite read-only mode.
It may safely be invoked later, even after original time windows have expired.
When a full source or snapshot audit fails, stop and retain the files; do not
edit original journal records, rename old CSVs or use retrospective backfill.

## What success does and does not mean

An offline `PASS_INTERNAL_CONSISTENCY_ONLY` means an owner-local, self-contained
backup can be opened and its copied data/manifest/journal relationships agree.
It is **not** a production database restoration, signed Alpaca provider
attestation, proof that the computer cannot fail, independent sealed research
validation, executable strategy, broker performance, or real-money readiness.
The snapshot is currently **unencrypted and stored on the same Mac**, so it
does not replace an encrypted off-device backup or formal disaster recovery.
Do not upload snapshots, raw CSVs or PAPER credentials to the source GitHub
repository. Obtain explicit approval and a separate reviewed security design
before connecting cloud storage or transferring backup bytes externally.

Fake-provider regression tests simulate 0/1/2 historical observation chains,
extra unlinked captures, no active-source modifications, independent backup
inodes and source/snapshot SHA checks, repeated names/path escape, partial
or missing raw evidence, tampered database/manifest/data, symlink rejection,
and separately named old journal segments. These are software tests; the real
owner-local snapshot is only verified once the owner runs the commands and
shares their **nonsecret JSON summary**.

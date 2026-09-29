# Phase 2O — disposable offline recovery and fault-injection drill

**Status:** Implemented, OFF by default, tested entirely on synthetic/fake
source data in CI. This is NOT a production database restore, an execution
path or an automatic daemon. The original active owner observation journal,
raw captures and Phase 2N immutable-name snapshot are never overwritten.

## Purpose

The owner has now reported a REAL Alpaca GET-only 3-observation journal,
verified its original source evidence (4 CSV/manifest pairs), created
`forward_20260929T070754_619609Z` as a separate owner-local snapshot
(9 verified copied file hashes), and subsequently rerun
`forward_snapshot --verify`, reporting
`PASS_INTERNAL_CONSISTENCY_ONLY` with 3 observations, 4 pairs and 9 hashes.
This is internal consistency of unsigned local evidence, not independent
market source authentication or profitability.

The Phase 2O tool tests a specific **scratch-only recovery scenario**:
can we reconstruct the complete archived forward-observation evidence
from that verified snapshot into disposable private files, then deliberately
break isolated copies and ensure **both** the raw-archive audit and the
snapshot-level SHA-manifest verification reject each fault?

## Exact owner command (manual; Mac terminal)

Pull the latest GitHub `main` through GitHub Desktop *when no hourly manual
capture is in progress*. In the activated `.venv`, run:

```sh
PYTHONPATH=src python -m signal_vault.forward_recovery_drill \
  --snapshot forward_20260929T070754_619609Z
```

`--snapshot` accepts ONLY an exact existing snapshot *folder basename*
under `data/forward/backups/`, not a path, arbitrary CSV, live journal, URL,
or external target. It first verifies the original owner-only 0700 archive
and all of its individual 0600 file hashes and observation chain. No new
capture or fresh-provider requirement applies because this is archived data.

Then the command creates disposable, independently copied temporary
directories in Git-ignored, private `data/forward/drills/`. It reopens a
fully copied SQLite journal and copied archived source CSVs/manifests,
checks all source fingerprints and their chain end to end, rejects any
shared disk inode with the archived files, and runs four **SEPARATE**
purposeful destructive scratch tests:

| Disposable fault | Required result |
|---|---|
| Alter one copied raw BTC/USD CSV | Both forensic and snapshot audits reject it |
| Change one copied CSV source manifest | Both audits reject it |
| Alter a copied SQLite numeric observation (or bootstrap SHA if zero observations) | Both audits reject it |
| Remove one copied capture manifest | Both audits reject it |

Each fault gets an independent disposable clone. No mutation function is
ever passed the original `data/forward/captures/`, active
`data/forward/observations.sqlite3`, or original saved
`data/forward/backups/<NAME>/` paths. The drill also re-verifies its
clean scratch recovery, compares the original snapshot's full inventory
SHA fingerprints before/after, and uses private temporary contexts for
cleanup even if a fault escapes detection or an exception occurs.
It refuses unsafe symlinks, world/group-readable backup or scratch
directories, snapshot names with path traversal, and insufficient free space.
Only a local 0600 lock file remains under `data/forward/drills/`;
the temporary evidence folders are removed.

Expected healthy output:
`PASS_ISOLATED_RECONSTRUCTION_AND_FAULT_REJECTION`, 3 recovered
observations, 4 recovered capture pairs, **10 source snapshot files checked**
(including its local unsigned snapshot manifest), and all four fault
scenarios marked `REJECTED_BY_BOTH_INDEPENDENT_CHECKS`. It must say
`active_journal_opened_or_modified=false`,
`original_snapshot_file_hashes_unchanged=true`,
`disposable_evidence_cleanup=COMPLETE`,
`network_requests=NONE`, `broker_order_submission=DISABLED`,
`automatic_scheduling=DISABLED`. The counts reflect this owner-reported
snapshot only; different snapshots may contain other legitimate counts.

If any stage fails, keep the original source journal and archived
snapshot unchanged and inspect the error. Do NOT delete/rename evidence,
rewrite a captured candle or use `forward_observer --bootstrap` on the
original journal. The test is intentionally **not an active restore**,
cannot prove offsite/disaster recovery (backup is currently same-device,
unsigned, unencrypted), and cannot authenticate provider records or
validate a trading strategy. Before any actual business-continuity plan,
separately design encrypted off-device copies, key handling, trusted
provenance and a controlled non-trading restore runbook.

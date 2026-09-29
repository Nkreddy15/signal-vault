"""Offline Phase 2O disaster/fault drill tests. Fake hourly source; zero networks."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from signal_vault.forward_capture import capture_current_window, default_capture_path
from signal_vault.forward_observer import ForwardObservationJournal
from signal_vault.forward_recovery_drill import run_forward_recovery_drill
from signal_vault.forward_snapshot import create_forward_snapshot, verify_forward_snapshot
from signal_vault.market_data import Bar

END = datetime(2026, 10, 7, 16, tzinfo=timezone.utc)


def sample(close):
    start=close-timedelta(hours=72)
    values=[]
    for index in range(72):
        stamp=start+timedelta(hours=index)
        offset=int((stamp-(END-timedelta(hours=72))).total_seconds()//3600)
        px=Decimal("120.123")+Decimal(offset)/Decimal("100")
        values.append(Bar(stamp, px, px+Decimal("1.5"), px-Decimal("0.5"),
                          px, Decimal("8"), "alpaca_crypto_us"))
    return tuple(values)


class FakeProvider:
    def __init__(self, data):
        self.data=data
    def fetch(self, *, start, end, as_of):
        return self.data


def prepare(root, *, count=3, name="verified_archive"):
    db=root/"observations.sqlite3"
    for i in range(count+1):
        close=END+timedelta(hours=i)
        clock=close+timedelta(minutes=7)
        dataset=sample(close)
        csv=root/"captures"/default_capture_path(clock).name
        manifest=capture_current_window(FakeProvider(dataset), now=clock, output_csv=csv)
        with ForwardObservationJournal(db, initialize=i==0) as journal:
            outcome=journal.process(dataset,csv_sha256=manifest.csv_sha256,
                                    observed_at=clock+timedelta(minutes=1),
                                    bootstrap=i==0)
            assert outcome["new_forward_observation_count"]==i
    created=create_forward_snapshot(root=root,name=name)
    assert created["prospective_observations_verified"]==count
    return db, root/"backups"/name


def sha(path):
    return sha256(path.read_bytes()).hexdigest()


class OfflineRecoveryDrillTests(unittest.TestCase):
    def test_3_observation_realistic_chain_reconstructs_and_rejects_all_four_faults(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward"
            journal,snapshot=prepare(root,count=3)
            journal_before=sha(journal)
            sources={str(path.relative_to(root)):sha(path)
                     for path in (root/"captures").glob("*") if path.is_file()}
            backup_before={str(path.relative_to(snapshot)):sha(path)
                           for path in snapshot.rglob("*") if path.is_file()}
            result=run_forward_recovery_drill(root=root,name=snapshot.name)
            self.assertEqual(result["result"],
                             "PASS_ISOLATED_RECONSTRUCTION_AND_FAULT_REJECTION")
            self.assertEqual(result["recovered_observations_verified"],3)
            self.assertEqual(result["recovered_capture_pairs_verified"],4)
            self.assertEqual(result["snapshot_files_checked"],10)
            self.assertEqual(len(result["injected_faults_rejected"]),4)
            self.assertEqual(set(result["injected_faults_rejected"].values()),
                             {"REJECTED_BY_BOTH_INDEPENDENT_CHECKS"})
            self.assertEqual(result["disposable_evidence_cleanup"],"COMPLETE")
            self.assertTrue(result["original_snapshot_file_hashes_unchanged"])
            self.assertFalse(result["active_journal_opened_or_modified"])
            self.assertEqual(result["network_requests"],"NONE")
            self.assertEqual(result["broker_order_submission"],"DISABLED")
            self.assertEqual(sha(journal),journal_before)
            self.assertEqual({str(path.relative_to(root)):sha(path)
                              for path in (root/"captures").glob("*") if path.is_file()},sources)
            self.assertEqual({str(path.relative_to(snapshot)):sha(path)
                              for path in snapshot.rglob("*") if path.is_file()},backup_before)
            self.assertEqual(verify_forward_snapshot(root=root,name=snapshot.name)
                             ["prospective_observations_verified"],3)
            self.assertFalse(list((root/"drills").glob(".isolated-recovery-*")))
            self.assertFalse(list((root/"drills").glob(".isolated-fault-*")))

    def test_bootstrap_only_works_without_observation_feature_table_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward"
            db,snapshot=prepare(root,count=0)
            before=sha(db)
            result=run_forward_recovery_drill(root=root,name=snapshot.name)
            self.assertEqual(result["recovered_observations_verified"],0)
            self.assertEqual(result["recovered_capture_pairs_verified"],1)
            self.assertEqual(len(result["injected_faults_rejected"]),4)
            self.assertEqual(sha(db),before)

    def test_one_observation_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward"
            _,archive=prepare(root,count=1)
            report=run_forward_recovery_drill(root=root,name=archive.name)
            self.assertEqual(report["recovered_observations_verified"],1)
            self.assertEqual(report["recovered_capture_pairs_verified"],2)

    def test_corrupted_source_backup_aborts_before_creating_scratch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward"
            journal,snapshot=prepare(root,count=1)
            before=sha(journal)
            file=sorted((snapshot/"captures").glob("*.csv"))[0]
            file.write_bytes(file.read_bytes()+b"altered real snapshot")
            with self.assertRaisesRegex(ValueError,"snapshot file SHA-256 mismatch"):
                run_forward_recovery_drill(root=root,name=snapshot.name)
            self.assertFalse((root/"drills").exists())
            self.assertEqual(sha(journal),before)

    def test_path_traversal_nonexisting_and_linked_snapshot_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward"
            _,snapshot=prepare(root,count=0)
            for name in ("../outside","/tmp/x","evil/sub",".hidden"):
                with self.subTest(name=name),self.assertRaisesRegex(ValueError,"name"):
                    run_forward_recovery_drill(root=root,name=name)
            with self.assertRaisesRegex(ValueError,"nonsymlink"):
                run_forward_recovery_drill(root=root,name="missing")
            linked=root/"backups"/"linked"
            linked.symlink_to(snapshot,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,"nonsymlink"):
                run_forward_recovery_drill(root=root,name=linked.name)
            self.assertFalse((root/"drills").exists())

    def test_unapproved_scratch_parent_symlink_and_public_mode_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward"
            _,snapshot=prepare(root,count=0)
            scratch=root/"drills"
            scratch.symlink_to(snapshot,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,"must not be symlinked"):
                run_forward_recovery_drill(root=root,name=snapshot.name)
            scratch.unlink()
            scratch.mkdir(mode=0o700)
            scratch.chmod(0o755)
            with self.assertRaisesRegex(PermissionError,"private"):
                run_forward_recovery_drill(root=root,name=snapshot.name)

    def test_injected_fault_that_goes_undetected_cannot_report_pass_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward"
            journal,snapshot=prepare(root,count=0)
            old=sha(journal)
            with patch("signal_vault.forward_recovery_drill._mutate_disposable_copy",
                       return_value=None):
                with self.assertRaisesRegex(AssertionError,"WAS NOT REJECTED"):
                    run_forward_recovery_drill(root=root,name=snapshot.name)
            self.assertEqual(sha(journal),old)
            self.assertEqual(verify_forward_snapshot(root=root,name=snapshot.name)
                             ["result"],"PASS_INTERNAL_CONSISTENCY_ONLY")
            self.assertFalse(list((root/"drills").glob(".isolated-*")))

    def test_insufficient_disk_blocks_before_copy_and_preserves_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward"
            journal,snapshot=prepare(root,count=0)
            before=sha(journal)
            from collections import namedtuple
            Disk=namedtuple("Disk","total used free")
            with patch("signal_vault.forward_recovery_drill.shutil.disk_usage",
                       return_value=Disk(1024,1024,0)):
                with self.assertRaisesRegex(OSError,"insufficient disk"):
                    run_forward_recovery_drill(root=root,name=snapshot.name)
            self.assertEqual(sha(journal),before)
            self.assertFalse(list((root/"drills").glob(".isolated-*")))


if __name__=="__main__":
    unittest.main()

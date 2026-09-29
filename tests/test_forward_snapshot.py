"""Offline forward snapshots: zero broker access, source-preserving backup/verification."""
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

from signal_vault.forward_capture import capture_current_window, default_capture_path
from signal_vault.forward_observer import ForwardObservationJournal
from signal_vault.forward_snapshot import create_forward_snapshot, verify_forward_snapshot
from signal_vault.market_data import Bar

END = datetime(2026, 10, 6, 16, tzinfo=timezone.utc)
ZERO_SHA = "a"*64


def bars(closed):
    start = closed-timedelta(hours=72)
    result = []
    for i in range(72):
        when = start+timedelta(hours=i)
        hour = int((when-(END-timedelta(hours=72))).total_seconds()//3600)
        px = Decimal("100.123")+Decimal(hour)/Decimal("100")
        result.append(Bar(when, px, px+Decimal("1"), px-Decimal("1"),
                          px, Decimal("100"), "alpaca_crypto_us"))
    return tuple(result)


class FakeProvider:
    def __init__(self, rows):
        self.rows=rows
        self.calls=0
    def fetch(self, *, start, end, as_of):
        self.calls += 1
        return self.rows


def make_chain(root, count=2, filename="observations.sqlite3"):
    db=root/filename
    for number in range(count+1):
        close=END+timedelta(hours=number)
        clock=close+timedelta(minutes=7)
        source=FakeProvider(bars(close))
        path=root/"captures"/default_capture_path(clock).name
        receipt=capture_current_window(source, now=clock, output_csv=path)
        with ForwardObservationJournal(db, initialize=number==0) as journal:
            result=journal.process(source.rows, csv_sha256=receipt.csv_sha256,
                                   observed_at=clock+timedelta(minutes=1),
                                   bootstrap=number==0)
            assert result["new_forward_observation_count"] == number
    return db


def sha(path):
    return sha256(path.read_bytes()).hexdigest()


class ForwardSnapshotTests(unittest.TestCase):
    def test_two_obs_backup_and_isolated_verify_preserve_every_source_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward"
            journal=make_chain(root,count=2)
            # A valid prior exploratory capture NOT part of this journal
            # must not be laundered into its immutable evidence snapshot.
            stray=END-timedelta(hours=1)
            stray_csv=root/"captures"/default_capture_path(
                stray+timedelta(minutes=7)).name
            capture_current_window(FakeProvider(bars(stray)),
                                   now=stray+timedelta(minutes=7),
                                   output_csv=stray_csv)
            source_hashes={str(p.relative_to(root)):sha(p)
                           for p in root.rglob("*") if p.is_file()}
            report=create_forward_snapshot(root=root,name="test_segment")
            self.assertEqual(report["prospective_observations_verified"],2)
            self.assertEqual(report["csv_manifest_pairs_verified"],3)
            self.assertEqual(report["file_hashes_verified"],7)
            self.assertFalse(report["original_journal_modified"])
            self.assertEqual(report["network_requests"],"NONE")
            self.assertEqual(report["broker_order_submission"],"DISABLED")
            snapshot=root/"backups"/"test_segment"
            self.assertEqual(snapshot.stat().st_mode & 0o777,0o700)
            self.assertEqual((snapshot/"observations.sqlite3").stat().st_mode & 0o777,0o600)
            self.assertFalse((snapshot/"captures"/stray_csv.name).exists())
            self.assertEqual(verify_forward_snapshot(root=root,name="test_segment")
                             ["result"],"PASS_INTERNAL_CONSISTENCY_ONLY")
            self.assertEqual({str(p.relative_to(root)):sha(p)
                              for p in root.rglob("*") if p.is_file()
                              and "backups" not in p.parts},source_hashes)
            with sqlite3.connect(snapshot/"observations.sqlite3") as conn:
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM forward_observations").fetchone()[0],2)
            with sqlite3.connect(journal) as conn:
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM forward_observations").fetchone()[0],2)

    def test_zero_obs_and_named_segment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward"
            named=make_chain(root,count=0,filename="observations-segment-02.sqlite3")
            report=create_forward_snapshot(root=root, db=named,
                                           name="named_segment")
            self.assertEqual(report["prospective_observations_verified"],0)
            self.assertEqual(report["csv_manifest_pairs_verified"],1)
            self.assertFalse((root/"observations.sqlite3").exists())
            verify=verify_forward_snapshot(root=root,name="named_segment")
            self.assertEqual(verify["prospective_observations_verified"],0)

    def test_repeated_name_path_escape_and_active_original_protected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward"
            db=make_chain(root,count=1)
            create_forward_snapshot(root=root,name="do_not_replace")
            before=sha(root/"backups"/"do_not_replace"/"observations.sqlite3")
            with self.assertRaises(FileExistsError):
                create_forward_snapshot(root=root,name="do_not_replace")
            self.assertEqual(sha(root/"backups"/"do_not_replace"/"observations.sqlite3"),before)
            for bad in ("../research", "..", "/tmp/foo", "evil/sub", ".secret"):
                with self.subTest(name=bad), self.assertRaises(ValueError):
                    create_forward_snapshot(root=root,name=bad)
            with self.assertRaisesRegex(ValueError,"under its own"):
                create_forward_snapshot(root=root,db=root/".."/"research"/"bad.sqlite3",
                                        name="outside")
            self.assertTrue(db.is_file())

    def test_tamper_snapshot_byte_or_manifest_fails_without_changing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward"
            db=make_chain(root,count=1)
            initial=sha(db)
            create_forward_snapshot(root=root,name="copy")
            snapshot=root/"backups"/"copy"
            archived=next((snapshot/"captures").glob("*.csv"))
            original=archived.read_bytes()
            archived.write_bytes(original+b"\n")
            with self.assertRaisesRegex(ValueError,"snapshot file SHA-256 mismatch"):
                verify_forward_snapshot(root=root,name="copy")
            archived.write_bytes(original)
            manifest=snapshot/"snapshot.manifest.json"
            data=json.loads(manifest.read_text())
            data["prospective_observations_verified"]=100
            manifest.write_text(json.dumps(data),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"count disagrees"):
                verify_forward_snapshot(root=root,name="copy")
            self.assertEqual(sha(db),initial)

    def test_missing_source_blocks_snapshot_without_partial_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward"
            make_chain(root,count=1)
            newest=root/"captures"/default_capture_path(
                END+timedelta(hours=1,minutes=7)).name
            newest.unlink()
            with self.assertRaisesRegex(ValueError,"nonsymlink"):
                create_forward_snapshot(root=root,name="must_fail")
            self.assertFalse((root/"backups"/"must_fail").exists())
            self.assertFalse(any((root/"backups").glob(".pending-forward-*")))

    def test_archive_metadata_additional_or_missing_files_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward"
            make_chain(root,count=0)
            create_forward_snapshot(root=root,name="copy")
            snapshot=root/"backups"/"copy"
            extra=snapshot/"unexpected.txt"
            extra.write_text("not part of capture chain")
            with self.assertRaisesRegex(ValueError,"unexpected"):
                verify_forward_snapshot(root=root,name="copy")
            extra.unlink()
            first=next((snapshot/"captures").glob("*.manifest.json"))
            first.unlink()
            with self.assertRaisesRegex(ValueError,"missing"):
                verify_forward_snapshot(root=root,name="copy")

    def test_dangling_symlink_inside_snapshot_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward"
            make_chain(root,count=0)
            create_forward_snapshot(root=root,name="clean_copy")
            folder=root/"backups"/"clean_copy"
            (folder/"dangling").symlink_to(folder/"file-that-does-not-exist")
            with self.assertRaisesRegex(ValueError,"no symbolic links"):
                verify_forward_snapshot(root=root,name="clean_copy")

    def test_snapshot_folder_and_database_symlink_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward"
            db=make_chain(root,count=0)
            alias=root/"backups"/"linked"
            alias.parent.mkdir(mode=0o700)
            alias.symlink_to(root,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,"nonsymlink"):
                verify_forward_snapshot(root=root,name="linked")
            with self.assertRaises(FileExistsError):
                create_forward_snapshot(root=root,name="linked")
            journal_alias=root/"aliased.sqlite3"
            journal_alias.symlink_to(db)
            with self.assertRaisesRegex(ValueError,"under its own"):
                create_forward_snapshot(root=root,db=journal_alias,name="invalid")


if __name__ == "__main__":
    unittest.main()

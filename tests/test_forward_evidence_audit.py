"""Offline archival provenance audit: fake-provider fixtures, no credentials/network/orders."""
import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from hashlib import sha256
from pathlib import Path

from signal_vault.forward_capture import capture_current_window, default_capture_path
from signal_vault.forward_evidence_audit import audit_forward_evidence
from signal_vault.forward_observer import ForwardObservationJournal
from signal_vault.market_data import Bar

END = datetime(2026, 10, 5, 13, tzinfo=timezone.utc)


def sample(closed: datetime, count=72):
    first = closed-timedelta(hours=count)
    rows = []
    for i in range(count):
        stamp = first+timedelta(hours=i)
        hour = int((stamp-(END-timedelta(hours=72))).total_seconds()/3600)
        price = D("100.12")+D(hour)/D("10")
        rows.append(Bar(stamp, price, price+D("1.2"), price-D("0.7"),
                        price, D("100"), "alpaca_crypto_us"))
    return tuple(rows)


class FakeGet:
    def __init__(self, closed):
        self.rows = sample(closed)
        self.calls = 0

    def fetch(self, *, start, end, as_of):
        self.calls += 1
        return self.rows


def setup_evidence(root: Path, *, n=1, db_name="observations.sqlite3"):
    db = root/db_name
    closed = END
    at = closed+timedelta(minutes=7)
    target = root/"captures"/default_capture_path(at).name
    provider = FakeGet(closed)
    boot_manifest = capture_current_window(provider, now=at, output_csv=target)
    with ForwardObservationJournal(db, initialize=True) as journal:
        first = journal.process(provider.rows, csv_sha256=boot_manifest.csv_sha256,
                                observed_at=at, bootstrap=True)
        assert first["new_forward_observation_count"] == 0
    for i in range(1,n+1):
        closed = END+timedelta(hours=i)
        at = closed+timedelta(minutes=7)
        source = FakeGet(closed)
        target = root/"captures"/default_capture_path(at).name
        manifest = capture_current_window(source, now=at, output_csv=target)
        with ForwardObservationJournal(db) as journal:
            result = journal.process(source.rows, csv_sha256=manifest.csv_sha256,
                                     observed_at=at+timedelta(minutes=1))
            assert result["new_forward_observation_count"] == i
    return db


class ArchivedEvidenceAuditTests(unittest.TestCase):
    def test_bootstrap_without_observations_is_verified_without_mutating_sqlite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/"forward"
            db = setup_evidence(root, n=0)
            before = sha256(db.read_bytes()).hexdigest()
            report = audit_forward_evidence(root=root)
            self.assertEqual(report["prospective_observations_verified"], 0)
            self.assertEqual(report["bootstrap_anchored_bars"], 72)
            self.assertEqual(report["archived_csv_manifest_pairs_verified"], 1)
            self.assertEqual(report["journal_modified"], False)
            self.assertEqual(report["network_requests"], "NONE")
            self.assertEqual(report["broker_order_submission"], "DISABLED")
            self.assertEqual(sha256(db.read_bytes()).hexdigest(), before)

    def test_one_and_two_prospective_observations_reconcile_entire_chain(self):
        for count in (1,2):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)/"forward"
                db = setup_evidence(root, n=count)
                before = db.read_bytes()
                result = audit_forward_evidence(root=root)
                self.assertEqual(result["result"], "PASS_INTERNAL_CONSISTENCY_ONLY")
                self.assertEqual(result["prospective_observations_verified"], count)
                self.assertEqual(result["archived_csv_manifest_pairs_verified"], count+1)
                self.assertEqual(db.read_bytes(), before)

    def test_reject_altered_bootstrap_and_missing_observation_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/"forward"
            setup_evidence(root, n=1)
            first = root/"captures"/default_capture_path(END+timedelta(minutes=7)).name
            first.write_bytes(first.read_bytes()+b"\n")
            with self.assertRaisesRegex(ValueError, "SHA mismatch"):
                audit_forward_evidence(root=root)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/"forward"
            setup_evidence(root, n=1)
            second = root/"captures"/default_capture_path(
                END+timedelta(hours=1,minutes=7)).name
            second.unlink()
            with self.assertRaisesRegex(ValueError, "existing nonsymlink"):
                audit_forward_evidence(root=root)

    def test_reject_changed_manifest_or_wrong_manifest_time(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/"forward"
            setup_evidence(root, n=1)
            second = root/"captures"/default_capture_path(
                END+timedelta(hours=1,minutes=7)).name
            meta = second.with_suffix(".csv.manifest.json")
            original = json.loads(meta.read_text())
            altered = dict(original, source="synthetic")
            meta.write_text(json.dumps(altered))
            with self.assertRaisesRegex(ValueError, "manifest provenance"):
                audit_forward_evidence(root=root)
            original["source"] = "alpaca_crypto_us"
            original["captured_utc"] = (END+timedelta(hours=2)).isoformat()
            meta.write_text(json.dumps(original))
            with self.assertRaisesRegex(ValueError, "outside original"):
                audit_forward_evidence(root=root)

    def test_reject_sqlite_feature_tampering_and_hash_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/"forward"
            db = setup_evidence(root,n=1)
            with sqlite3.connect(db) as conn:
                conn.execute("UPDATE forward_observations SET close_usd='9999'")
            with self.assertRaisesRegex(ValueError, "features differ"):
                audit_forward_evidence(root=root)
            with sqlite3.connect(db) as conn:
                conn.execute("UPDATE forward_observations SET close_usd=?",
                             (str(sample(END+timedelta(hours=1))[-1].close),))
                conn.execute("UPDATE captured_bar_hashes SET bar_sha256='0' WHERE start_utc=?",
                             ((END-timedelta(hours=1)).isoformat(),))
            with self.assertRaisesRegex(ValueError, "anchored candle hashes"):
                audit_forward_evidence(root=root)

    def test_reject_observation_time_rewriting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/"forward"
            db = setup_evidence(root,n=1)
            with sqlite3.connect(db) as conn:
                conn.execute("UPDATE forward_observations SET observed_utc=?",
                             ((END+timedelta(hours=2,minutes=8)).isoformat(),))
            with self.assertRaisesRegex(ValueError, "retrospective"):
                audit_forward_evidence(root=root)

    def test_missing_journal_insecure_journal_and_outside_paths_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/"forward"
            (root/"captures").mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "existing nonsymlink"):
                audit_forward_evidence(root=root)
            db = setup_evidence(root,n=0)
            db.chmod(0o644)
            with self.assertRaisesRegex(PermissionError, "0600"):
                audit_forward_evidence(root=root)
            db.chmod(0o600)
            with self.assertRaisesRegex(ValueError, "within data/forward"):
                audit_forward_evidence(root=root, db=root/".."/"outside.sqlite3")
            other = root/"segment.sqlite3"
            other.symlink_to(db)
            with self.assertRaisesRegex(ValueError, "existing nonsymlink"):
                audit_forward_evidence(root=root, db=other)

    def test_named_explicit_segment_supported_without_modifying_primary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/"forward"
            secondary = setup_evidence(root, n=0, db_name="observations-segment-02.sqlite3")
            report = audit_forward_evidence(root=root,db=secondary)
            self.assertEqual(report["prospective_observations_verified"],0)
            self.assertFalse((root/"observations.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()

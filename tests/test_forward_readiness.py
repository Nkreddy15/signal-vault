"""Offline next-hour readiness classification. No provider network or real orders."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from hashlib import sha256
from pathlib import Path

from signal_vault.forward_capture import capture_current_window, default_capture_path
from signal_vault.forward_observer import ForwardObservationJournal
from signal_vault.forward_readiness import forward_readiness
from signal_vault.market_data import Bar

END = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)


def sample(closed: datetime):
    start = closed-timedelta(hours=72)
    rows = []
    for i in range(72):
        hour = start+timedelta(hours=i)
        absolute = int((hour-(END-timedelta(hours=72))).total_seconds()/3600)
        px = D("105")+D(absolute)/D("100")
        rows.append(Bar(hour,px,px+D("1"),px-D("1"),px,D("100"),"alpaca_crypto_us"))
    return tuple(rows)


class FakeData:
    def __init__(self, closed):
        self.bars = sample(closed)
    def fetch(self, *,start,end,as_of):
        return self.bars


def established(root: Path, *, n: int = 1, db_name: str = "observations.sqlite3"):
    db = root/db_name
    for index in range(n+1):
        closed = END+timedelta(hours=index)
        at = closed+timedelta(minutes=7)
        source = FakeData(closed)
        csv = root/"captures"/default_capture_path(at).name
        manifest = capture_current_window(source,now=at,output_csv=csv)
        with ForwardObservationJournal(db, initialize=index==0) as journal:
            response = journal.process(source.bars,csv_sha256=manifest.csv_sha256,
                                       observed_at=at+timedelta(minutes=1),
                                       bootstrap=index==0)
            assert response["new_forward_observation_count"] == index
    return db


class ForwardReadinessTests(unittest.TestCase):
    def test_time_windows_without_any_file_or_journal_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward"
            db=established(root)
            next_close=END+timedelta(hours=2)
            samples=(
                (next_close-timedelta(minutes=1),"WAIT_NEXT_HOURLY_CANDLE_TO_CLOSE"),
                (next_close+timedelta(minutes=2),"WAIT_THREE_MINUTES_FOR_CANDLE_PUBLICATION"),
                (next_close+timedelta(minutes=3),"READY_FOR_ONE_EXPLICIT_READ_ONLY_MANUAL_CYCLE"),
                (next_close+timedelta(minutes=24, seconds=59),"READY_FOR_ONE_EXPLICIT_READ_ONLY_MANUAL_CYCLE"),
                (next_close+timedelta(minutes=25),"MANUAL_CAPTURE_START_WINDOW_CLOSED"),
                (next_close+timedelta(hours=1),"MISSED_CONSECUTIVE_HOUR_PRESERVE_SEGMENT"),
            )
            old_bytes=db.read_bytes()
            original={p.name:sha256(p.read_bytes()).hexdigest()
                      for p in (root/"captures").glob("*")}
            for moment,expected in samples:
                with self.subTest(moment=moment):
                    result=forward_readiness(root=root,now=moment)
                    self.assertEqual(result["decision"],expected)
                    self.assertEqual(result["existing_prospective_observations"],1)
                    self.assertEqual(result["next_new_bar_closed_utc"],next_close.isoformat())
                    self.assertEqual(result["evidence"],"PASS_INTERNAL_CONSISTENCY_ONLY")
                    self.assertEqual(result["network_requests"],"NONE")
                    self.assertFalse(result["journal_modified"])
                    self.assertFalse(result["credentials_requested"])
                    self.assertEqual(result["broker_order_submission"],"DISABLED")
                    self.assertEqual(db.read_bytes(),old_bytes)
            self.assertEqual({p.name:sha256(p.read_bytes()).hexdigest()
                              for p in (root/"captures").glob("*")},original)

    def test_existing_fresh_capture_cannot_be_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward"
            established(root)
            next_close=END+timedelta(hours=2)
            at=next_close+timedelta(minutes=5)
            capture=root/"captures"/default_capture_path(at).name
            capture_current_window(FakeData(next_close),now=at,output_csv=capture)
            response=forward_readiness(root=root,now=at+timedelta(minutes=1))
            self.assertEqual(response["decision"],"CURRENT_CAPTURE_EXISTS_REVIEW_MANUAL_APPEND")
            self.assertIn("--observe --csv",response["operator_instruction"])
            self.assertNotIn("manual_forward_cycle",response["operator_instruction"])
            self.assertEqual(response["existing_prospective_observations"],1)
            self.assertEqual(forward_readiness(root=root,
                            now=at+timedelta(minutes=40))["decision"],
                            "HALT_EXISTING_CAPTURE_NOT_CURRENT_OR_NOT_VERIFIED")

    def test_incomplete_capture_pair_and_symlink_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward"
            established(root)
            at=END+timedelta(hours=2,minutes=4)
            capture=root/"captures"/default_capture_path(at).name
            capture.write_text("incomplete source",encoding="utf-8")
            self.assertEqual(forward_readiness(root=root,now=at)["decision"],
                             "HALT_INCOMPLETE_CAPTURE_PAIR")
            capture.unlink()
            capture.symlink_to(root/"observations.sqlite3")
            self.assertEqual(forward_readiness(root=root,now=at)["decision"],
                             "HALT_EXISTING_CAPTURE_SYMLINK")

    def test_archival_audit_failure_blocks_readiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward"
            established(root)
            original=root/"captures"/default_capture_path(END+timedelta(minutes=7)).name
            original.write_bytes(original.read_bytes()+b"tampered")
            with self.assertRaisesRegex(ValueError,"SHA mismatch"):
                forward_readiness(root=root,now=END+timedelta(hours=2, minutes=8))

    def test_clock_rollback_naive_clock_and_custom_segment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward"
            secondary=established(root,n=0,db_name="observations-segment-02.sqlite3")
            with self.assertRaisesRegex(ValueError,"timezone-aware"):
                forward_readiness(root=root,db=secondary,now=END)
            behind=forward_readiness(root=root,db=secondary,
                                     now=END+timedelta(minutes=6))
            self.assertEqual(behind["decision"],"HALT_LOCAL_CLOCK_BEHIND_JOURNAL")
            ready=forward_readiness(root=root,db=secondary,
                                    now=END+timedelta(hours=1,minutes=7))
            self.assertEqual(ready["decision"],"READY_FOR_ONE_EXPLICIT_READ_ONLY_MANUAL_CYCLE")
            self.assertIn("--db",ready["operator_instruction"])
            self.assertIn(str(secondary),ready["operator_instruction"])
            self.assertFalse((root/"observations.sqlite3").exists())

    def test_missing_journal_does_not_create_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward"
            (root/"captures").mkdir(parents=True)
            with self.assertRaisesRegex(ValueError,"existing nonsymlink"):
                forward_readiness(root=root,now=END+timedelta(minutes=6))
            self.assertFalse((root/"observations.sqlite3").exists())


if __name__=="__main__":
    unittest.main()

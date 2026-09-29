"""Manual one-command forward cycle: explicit GET-only and journal safety tests."""
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from pathlib import Path

from signal_vault.forward_observer import ForwardObservationJournal
from signal_vault.manual_forward_cycle import (
    capture_and_observe, plan_manual_observation,
)
from signal_vault.market_data import Bar
from signal_vault.runtime_lock import RuntimeAlreadyLocked, RuntimeFileLock

END = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
BOOT_AT = END + timedelta(minutes=7)
DUE = END + timedelta(hours=1, minutes=7)
BOOT_SHA = "a" * 64


def synthetic(end: datetime, count=72):
    first = end - timedelta(hours=count)
    rows = []
    for i in range(count):
        stamp = first + timedelta(hours=i)
        absolute_hour = int((stamp - (END - timedelta(hours=72))).total_seconds() // 3600)
        px = D("100") + D(absolute_hour) / D("10")
        rows.append(Bar(stamp, px, px + D("10"), px - D("10"),
                        px, D("100"), "alpaca_crypto_us"))
    return tuple(rows)


class FakeGetProvider:
    def __init__(self, bars):
        self.bars = bars
        self.calls = []

    def fetch(self, *, start, end, as_of):
        self.calls.append((start, end, as_of))
        return self.bars


def bootstrap(root: Path):
    with ForwardObservationJournal(root / "observations.sqlite3", initialize=True) as journal:
        result = journal.process(synthetic(END), csv_sha256=BOOT_SHA,
                                 observed_at=BOOT_AT, bootstrap=True)
    assert result["new_forward_observation_count"] == 0


class ManualForwardCycleTests(unittest.TestCase):
    def test_preflight_and_single_manual_get_append(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "forward"
            bootstrap(root)
            planned = plan_manual_observation(root=root, now=DUE)
            self.assertEqual(planned["expected_closed_utc"],
                             (END+timedelta(hours=1)).isoformat())
            self.assertEqual(planned["expected_candle_started_utc"], END.isoformat())
            self.assertIn("btcusd_72h_end_20261003T1300Z.csv", planned["target_csv"])
            provider = FakeGetProvider(synthetic(END+timedelta(hours=1)))
            result = capture_and_observe(provider, now=DUE, root=root,
                                         after_capture_now=lambda: DUE+timedelta(minutes=1))
            self.assertEqual(len(provider.calls), 1)
            self.assertEqual(provider.calls[0][:2],
                             (END-timedelta(hours=71), END+timedelta(hours=1)))
            self.assertEqual(result["journal"]["new_forward_observation_count"], 1)
            self.assertEqual(result["journal"]["outcome"], "ONE_NEW_CLOSED_BAR_RECORDED_NO_TRADE")
            self.assertEqual(result["journal"]["latest_forward_observation"]["bar_started_utc"],
                             END.isoformat())
            self.assertEqual(result["paper_order_submission"], "DISABLED")
            self.assertEqual(result["automatic_scheduling"], "DISABLED")
            self.assertTrue(Path(result["capture_csv"]).is_file())
            self.assertTrue(Path(result["capture_manifest"]).is_file())
            self.assertEqual(Path(result["capture_csv"]).stat().st_mode & 0o777, 0o600)
            with ForwardObservationJournal(root / "observations.sqlite3") as journal:
                self.assertEqual(journal.status()["new_forward_observation_count"], 1)

    def test_early_missed_late_and_repeated_preflight_never_get_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "forward"
            bootstrap(root)
            provider = FakeGetProvider(synthetic(END+timedelta(hours=1)))
            cases = (
                (END + timedelta(minutes=7), "has not closed"),
                (END + timedelta(hours=1, minutes=2), "between UTC minute"),
                (END + timedelta(hours=1, minutes=25), "between UTC minute"),
                (END + timedelta(hours=2, minutes=7), "hour missed"),
            )
            for moment, message in cases:
                with self.subTest(moment=moment), self.assertRaisesRegex(ValueError, message):
                    capture_and_observe(provider, now=moment, root=root)
            self.assertEqual(provider.calls, [])
            with ForwardObservationJournal(root / "observations.sqlite3") as journal:
                self.assertEqual(journal.status()["new_forward_observation_count"], 0)

    def test_original_capture_is_preserved_if_overlap_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "forward"
            bootstrap(root)
            broken = list(synthetic(END+timedelta(hours=1)))
            broken[-2] = replace(broken[-2], close=broken[-2].close+D("1"))
            provider = FakeGetProvider(broken)
            with self.assertRaisesRegex(RuntimeError, "raw capture retained"):
                capture_and_observe(provider, now=DUE, root=root,
                                    after_capture_now=lambda: DUE+timedelta(minutes=1))
            target = root / "captures" / "btcusd_72h_end_20261003T1300Z.csv"
            self.assertTrue(target.is_file())
            self.assertTrue(target.with_suffix(".csv.manifest.json").is_file())
            with ForwardObservationJournal(root / "observations.sqlite3") as journal:
                self.assertEqual(journal.status()["new_forward_observation_count"], 0)
            with self.assertRaisesRegex(ValueError, "already exists"):
                capture_and_observe(FakeGetProvider(synthetic(END+timedelta(hours=1))),
                                    now=DUE, root=root)

    def test_capture_crossing_new_hour_preserves_raw_data_without_append(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "forward"
            bootstrap(root)
            provider = FakeGetProvider(synthetic(END+timedelta(hours=1)))
            with self.assertRaisesRegex(RuntimeError, "raw capture retained"):
                capture_and_observe(provider, now=DUE, root=root,
                                    after_capture_now=lambda: END+timedelta(hours=2, minutes=1))
            self.assertTrue((root / "captures" / "btcusd_72h_end_20261003T1300Z.csv").exists())
            with ForwardObservationJournal(root / "observations.sqlite3") as journal:
                self.assertEqual(journal.status()["new_forward_observation_count"], 0)

    def test_missing_journal_and_symlink_path_refused_pre_get(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "forward"
            with self.assertRaisesRegex(ValueError, "missing"):
                plan_manual_observation(root=root, now=DUE)
            bootstrap(root)
            alias = Path(temp) / "forward-symlink"
            alias.symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "not a symlink"):
                plan_manual_observation(root=alias, now=DUE)

    def test_second_invocation_when_lock_held_does_not_capture(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "forward"
            bootstrap(root)
            provider = FakeGetProvider(synthetic(END+timedelta(hours=1)))
            with RuntimeFileLock(root / ".manual_forward_cycle.lock"):
                with self.assertRaises(RuntimeAlreadyLocked):
                    capture_and_observe(provider, now=DUE, root=root)
            self.assertEqual(provider.calls, [])
            self.assertFalse((root / "captures").exists())

    def test_successful_same_hour_repeat_is_refused_without_get(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "forward"
            bootstrap(root)
            provider = FakeGetProvider(synthetic(END+timedelta(hours=1)))
            capture_and_observe(provider, now=DUE, root=root,
                                after_capture_now=lambda: DUE+timedelta(minutes=1))
            with self.assertRaisesRegex(ValueError, "has not closed"):
                capture_and_observe(provider, now=DUE+timedelta(minutes=2), root=root)
            self.assertEqual(len(provider.calls), 1)


if __name__ == "__main__":
    unittest.main()

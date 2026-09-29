"""Local-only forward data observation, provenance and fail-closed regression tests."""
import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from hashlib import sha256
from pathlib import Path

from signal_vault.data_capture import capture_dataset
from signal_vault.forward_capture import capture_current_window, default_capture_path, _read_data_get_no_redirect
from signal_vault.forward_observer import (
    ForwardObservationJournal, _bar_sha256, _local_forward_path, read_verified_capture,
)
from signal_vault.market_data import Bar

END = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
NOW = END + timedelta(minutes=7)
FIRST_SHA = "a" * 64
SECOND_SHA = "b" * 64


def sample(end=END, n=72):
    start = end - timedelta(hours=n)
    result = []
    for i in range(n):
        stamp = start + timedelta(hours=i)
        # The price is a pure function of absolute candle time, not of the
        # rolling 72-hour capture window's changing array index.
        absolute_hour = int((stamp - (END - timedelta(hours=72))).total_seconds() // 3600)
        px = D("100") + D(absolute_hour) / D("10")
        result.append(Bar(
            stamp, px, px + D("10"), px - D("10"),
            px, D("100"), "alpaca_crypto_us",
        ))
    return tuple(result)


class FakeProvider:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def fetch(self, *, start, end, as_of):
        self.calls.append((start, end, as_of))
        return self.rows


class ForwardObservationJournalTests(unittest.TestCase):
    def test_bootstrap_no_hindsight_then_one_new_bar_once(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "observation.sqlite3"
            initial = sample()
            next_rows = sample(END + timedelta(hours=1))
            with ForwardObservationJournal(db, initialize=True) as journal:
                boot = journal.process(initial, csv_sha256=FIRST_SHA,
                                       observed_at=NOW, bootstrap=True)
                self.assertEqual(boot["new_forward_observation_count"], 0)
                self.assertEqual(boot["outcome"], "BOOTSTRAPPED_HISTORY_ONLY_NO_RETROSPECTIVE_SIGNALS")
                self.assertIsNone(boot["latest_forward_observation"])
                self.assertEqual(db.stat().st_mode & 0o777, 0o600)
                with self.assertRaises(ValueError):
                    journal.process(initial, csv_sha256=FIRST_SHA,
                                    observed_at=NOW, bootstrap=True)
            with ForwardObservationJournal(db) as journal:
                new = journal.process(next_rows, csv_sha256=SECOND_SHA,
                                      observed_at=NOW + timedelta(hours=1))
                self.assertEqual(new["outcome"], "ONE_NEW_CLOSED_BAR_RECORDED_NO_TRADE")
                self.assertEqual(new["new_forward_observation_count"], 1)
                obs = new["latest_forward_observation"]
                self.assertEqual(obs["bar_started_utc"], END.isoformat())
                self.assertEqual(obs["bar_closed_utc"], (END + timedelta(hours=1)).isoformat())
                self.assertGreater(D(obs["modeled_round_trip_break_even_bps"]), D("0"))
                duplicate = journal.process(next_rows, csv_sha256=SECOND_SHA,
                                            observed_at=NOW + timedelta(hours=1, minutes=1))
                self.assertEqual(duplicate["outcome"], "ALREADY_OBSERVED_NO_DUPLICATE")
                self.assertEqual(duplicate["new_forward_observation_count"], 1)
                self.assertEqual(new["paper_order_submission"], "DISABLED")
                with self.assertRaises((OSError, ValueError)):
                    ForwardObservationJournal(db, initialize=True)

    def test_captured_bar_cannot_be_reclassified_as_forward_after_next_utc_hour(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "observations.sqlite3"
            with ForwardObservationJournal(db, initialize=True) as journal:
                # 65 minutes after the latest candle closed is within the old
                # 90-minute allowance, but the next completed UTC bar exists.
                # Refuse even bootstrapping such a late window.
                with self.assertRaisesRegex(ValueError, "stale for prospective"):
                    journal.process(sample(), csv_sha256=FIRST_SHA,
                                    observed_at=END + timedelta(minutes=65),
                                    bootstrap=True)
                self.assertEqual(journal.connection.execute(
                    "SELECT COUNT(*) FROM forward_state").fetchone()[0], 0)
                # Current UTC-hour bootstrap remains valid.
                journal.process(sample(), csv_sha256=FIRST_SHA,
                                observed_at=NOW, bootstrap=True)
                # At 65m past the *next* bar's close, even an otherwise
                # continuous one-bar capture may not be added retroactively.
                with self.assertRaisesRegex(ValueError, "stale for prospective"):
                    journal.process(sample(END+timedelta(hours=1)),
                                    csv_sha256=SECOND_SHA,
                                    observed_at=END+timedelta(hours=2, minutes=5))
                self.assertEqual(journal.status()["new_forward_observation_count"], 0)

    def test_existing_journal_requires_private_file_mode(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "observation.sqlite3"
            with ForwardObservationJournal(db, initialize=True) as journal:
                journal.process(sample(), csv_sha256=FIRST_SHA,
                                observed_at=NOW, bootstrap=True)
            db.chmod(0o644)
            with self.assertRaisesRegex(PermissionError, "0600"):
                ForwardObservationJournal(db)
            db.chmod(0o600)
            with ForwardObservationJournal(db) as journal:
                self.assertEqual(journal.status()["new_forward_observation_count"], 0)

    def test_changed_overlapping_candle_fails_and_does_not_append(self):
        with tempfile.TemporaryDirectory() as root:
            with ForwardObservationJournal(Path(root) / "db.sqlite3", initialize=True) as journal:
                journal.process(sample(), csv_sha256=FIRST_SHA, observed_at=NOW, bootstrap=True)
                changed = list(sample(END + timedelta(hours=1)))
                changed[-2] = replace(changed[-2], close=changed[-2].close + D("1"))
                with self.assertRaisesRegex(ValueError, "anchored"):
                    journal.process(changed, csv_sha256=SECOND_SHA,
                                    observed_at=NOW + timedelta(hours=1))
                self.assertEqual(journal.status()["new_forward_observation_count"], 0)
                self.assertEqual(journal.status()["latest_anchored_bar_start_utc"],
                                 (END - timedelta(hours=1)).isoformat())

    def test_missed_hours_do_not_become_hindsight_forward_observations(self):
        with tempfile.TemporaryDirectory() as root:
            with ForwardObservationJournal(Path(root) / "db.sqlite3", initialize=True) as journal:
                journal.process(sample(), csv_sha256=FIRST_SHA, observed_at=NOW, bootstrap=True)
                missed = sample(END + timedelta(hours=2))
                with self.assertRaisesRegex(ValueError, "missed forward observation"):
                    journal.process(missed, csv_sha256=SECOND_SHA,
                                    observed_at=NOW + timedelta(hours=2))
                self.assertEqual(journal.status()["new_forward_observation_count"], 0)

    def test_stale_future_gap_and_unbootstrapped_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "db.sqlite3"
            with ForwardObservationJournal(p, initialize=True) as journal:
                with self.assertRaisesRegex(ValueError, "explicit bootstrap"):
                    journal.process(sample(), csv_sha256=FIRST_SHA, observed_at=NOW)
                with self.assertRaisesRegex(ValueError, "stale"):
                    journal.process(sample(), csv_sha256=FIRST_SHA,
                                    observed_at=END + timedelta(hours=3), bootstrap=True)
                with self.assertRaisesRegex(ValueError, "open / future"):
                    journal.process(sample(), csv_sha256=FIRST_SHA,
                                    observed_at=END - timedelta(minutes=1), bootstrap=True)
                broken = list(sample())
                del broken[-2]
                with self.assertRaisesRegex(ValueError, "missing hourly bar"):
                    journal.process(broken, csv_sha256=FIRST_SHA,
                                    observed_at=NOW, bootstrap=True)
                self.assertEqual(journal.connection.execute(
                    "SELECT COUNT(*) FROM forward_state").fetchone()[0], 0)

    def test_canonical_bar_hash_accepts_same_values_different_decimal_scale(self):
        with tempfile.TemporaryDirectory() as root:
            with ForwardObservationJournal(Path(root) / "db.sqlite3", initialize=True) as journal:
                journal.process(sample(), csv_sha256=FIRST_SHA, observed_at=NOW, bootstrap=True)
                values = list(sample(END + timedelta(hours=1)))
                values[-2] = replace(values[-2], close=D(str(values[-2].close) + "0"))
                # Explicit decimal scale change (not a price change).
                values[-2] = replace(values[-2], close=values[-2].close.quantize(D("0.0000")))
                next_status = journal.process(values, csv_sha256=SECOND_SHA,
                                              observed_at=NOW + timedelta(hours=1))
                self.assertEqual(next_status["new_forward_observation_count"], 1)

    def test_overlapping_candle_hash_preserves_more_than_28_significant_digits(self):
        original = replace(sample()[-1],
                           close=D("107.123456789012345678901234567891"))
        modified = replace(original,
                           close=D("107.123456789012345678901234567892"))
        self.assertNotEqual(_bar_sha256(original), _bar_sha256(modified))
        self.assertEqual(
            _bar_sha256(replace(original, close=D("107.1234567890123456789012345678910"))),
            _bar_sha256(original),
        )

    def test_observation_clock_cannot_move_backwards(self):
        with tempfile.TemporaryDirectory() as root:
            with ForwardObservationJournal(Path(root) / "db.sqlite3", initialize=True) as journal:
                journal.process(sample(), csv_sha256=FIRST_SHA,
                                observed_at=NOW, bootstrap=True)
                # Reuse the already fully closed window, so the test reaches
                # the clock guard instead of the earlier future-bar guard.
                with self.assertRaisesRegex(ValueError, "clock moved backwards"):
                    journal.process(sample(), csv_sha256=SECOND_SHA,
                                    observed_at=NOW - timedelta(minutes=1))
                self.assertEqual(journal.status()["new_forward_observation_count"], 0)

    def test_verified_provenance_and_capture_freshness(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "latest_72h.csv"
            provider = FakeProvider(sample())
            manifest = capture_current_window(provider, now=NOW, output_csv=p)
            self.assertEqual(manifest.row_count, 72)
            self.assertEqual(provider.calls[0][:2], (END - timedelta(hours=72), END))
            self.assertTrue(str(default_capture_path(NOW)).endswith("btcusd_72h_end_20261002T1200Z.csv"))
            with self.assertRaisesRegex(ValueError, "immutable"):
                capture_current_window(provider, now=NOW, output_csv=p)
            self.assertEqual(len(provider.calls), 1)
            bars, digest = read_verified_capture(p, observed_at=NOW)
            self.assertEqual(len(bars), 72)
            self.assertEqual(digest, sha256(p.read_bytes()).hexdigest())
            with self.assertRaisesRegex(ValueError, "stale"):
                read_verified_capture(p, observed_at=NOW + timedelta(minutes=31))
            p.write_bytes(p.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                read_verified_capture(p, observed_at=NOW)

    def test_manifest_source_and_future_capture_fail(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "latest_72h.csv"
            capture_dataset(FakeProvider(sample()), start=END-timedelta(hours=72), end=END,
                            as_of=NOW, output_csv=p, captured_at=NOW)
            meta = p.with_suffix(p.suffix + ".manifest.json")
            payload = json.loads(meta.read_text())
            payload["source"] = "synthetic"
            meta.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "provenance"):
                read_verified_capture(p, observed_at=NOW)
            payload["source"] = "alpaca_crypto_us"
            payload["captured_utc"] = (NOW + timedelta(hours=1)).isoformat()
            meta.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "future-dated"):
                read_verified_capture(p, observed_at=NOW)

    def test_cli_path_boundaries_refuse_research_files(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root) / "data" / "forward"
            self.assertEqual(_local_forward_path(str(root / "recent.csv"), root=root),
                             (root / "recent.csv").resolve())
            with self.assertRaisesRegex(ValueError, "within data/forward"):
                _local_forward_path(str(root / ".." / "research" / "holdout.csv"), root=root)

    def test_prospective_capture_refuses_too_early_and_provider_gap(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "recent.csv"
            with self.assertRaisesRegex(ValueError, "three minutes"):
                capture_current_window(FakeProvider(sample()),
                    now=END+timedelta(minutes=1), output_csv=p)
            incomplete = list(sample())
            del incomplete[10]
            with self.assertRaisesRegex(ValueError, "missing hourly bar"):
                capture_current_window(FakeProvider(incomplete), now=NOW, output_csv=p)
            self.assertFalse(p.exists())

    def test_data_transport_allowlist_rejects_non_get_hosts_without_request(self):
        urls = (
            "https://paper-api.alpaca.markets/v2/orders?symbols=BTC/USD",
            "https://api.alpaca.markets/v2/orders",
            "http://data.alpaca.markets/v1beta3/crypto/us/bars",
            "https://data.alpaca.markets/v1beta3/crypto/us/bars?symbols=BTC/USD",
        )
        for url in urls:
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "allowlist"):
                _read_data_get_no_redirect(url, "paper-key", "paper-secret")


if __name__ == "__main__":
    unittest.main()

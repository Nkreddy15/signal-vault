"""Isolated cloud-ready forward worker: entirely fake providers and temp volumes.

No Docker activation, real file-mounted credentials, network, PAPER account,
Keychain, orders, trading worker or money is used in CI.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from signal_vault.cloud_forward_service import (
    _cloud_credentials, _private_volume, _write_shadow_receipt, cloud_cycle_once,
    cloud_preflight, cloud_status, next_due_utc,
)
from signal_vault.market_data import Bar
from signal_vault.paper_credentials import PaperCredentials
from signal_vault.shadow_signal_snapshot import inspect_latest_shadow_signal

END = datetime(2026, 9, 29, 18, 0, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)


def synthetic(closed):
    start = closed - 72 * HOUR
    out = []
    for i in range(72):
        at = start + i * HOUR
        n = int((at - (END - 72 * HOUR)).total_seconds() / 3600)
        p = Decimal("80000") + Decimal(n * 4)
        out.append(Bar(at, p, p + 8, p - 8, p, Decimal("10"),
                       "alpaca_crypto_us"))
    return tuple(out)


class FakeBars:
    def __init__(self, candles):
        self.candles = candles
        self.requests = 0

    def fetch(self, *, start, end, as_of):
        self.requests += 1
        return self.candles


def captured_files(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*") if p.is_file()
    }


class CloudSecretAndSchedulerTests(unittest.TestCase):
    def test_secret_file_reads_only_fixed_nonwritable_regular_files(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            k, s = base/"key", base/"secret"
            k.write_text("SENTINEL_DATA_KEY", encoding="utf-8")
            s.write_text("SENTINEL_DATA_SECRET", encoding="utf-8")
            k.chmod(0o600); s.chmod(0o400)
            with patch.dict(os.environ, {}, clear=True):
                result = _cloud_credentials(k, s)
            self.assertEqual(result.key_id, "SENTINEL_DATA_KEY")
            self.assertEqual(result.secret_key, "SENTINEL_DATA_SECRET")
            self.assertNotIn("SENTINEL", repr(result))
            s.chmod(0o622)
            with self.assertRaises(PermissionError):
                _cloud_credentials(k, s, {})
            s.chmod(0o600)
            link = base/"link"
            link.symlink_to(s)
            with self.assertRaises(ValueError):
                _cloud_credentials(k, link, {})
            k.write_text("SENTINEL_DATA_KEY\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                _cloud_credentials(k, s, {})

    def test_env_cannot_supply_generic_live_or_paper_order_credentials(self):
        with tempfile.TemporaryDirectory() as td:
            k, s = Path(td)/"k", Path(td)/"s"
            for item, value in ((k, "k"), (s, "s")):
                item.write_text(value); item.chmod(0o600)
            for name in ("ALPACA_PAPER_KEY_ID", "ALPACA_LIVE_KEY_ID",
                         "SIGNAL_VAULT_ENABLE_PAPER_ORDERS", "APCA_API_SECRET_KEY"):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    _cloud_credentials(k, s, {name: "1"})

    def test_secret_must_not_be_in_preflight_report_or_loaded_from_cloud_status(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)/"forward"
            root.mkdir(mode=0o700)
            calls = []
            def loader():
                calls.append(1)
                return PaperCredentials("SENTINEL_ABC", "SENTINEL_XYZ")
            pre = cloud_preflight(root=root, credential_loader=loader)
            self.assertEqual(pre["status"],
                             "LOCAL_CLOUD_PREFLIGHT_PASSED_NO_DEPLOYMENT")
            self.assertEqual(calls, [1])
            self.assertEqual(pre["network_requests"], "NONE")
            self.assertFalse(pre["cloud_service_activated"])
            self.assertNotIn("SENTINEL", json.dumps(pre))
            sta = cloud_status(root=root)
            self.assertEqual(sta["credential_access"], "NONE")
            self.assertEqual(sta["broker_order_submission"], "DISABLED")

    def test_scheduled_utc_slot_late_start_and_missed_hour(self):
        self.assertEqual(
            next_due_utc(END + timedelta(minutes=4)),
            END + timedelta(minutes=7))
        self.assertEqual(
            next_due_utc(END + timedelta(minutes=7, seconds=10)),
            END + timedelta(minutes=7, seconds=10))
        self.assertEqual(
            next_due_utc(END + timedelta(minutes=24, seconds=59)),
            END + timedelta(minutes=24, seconds=59))
        self.assertEqual(
            next_due_utc(END + timedelta(minutes=25)),
            END + HOUR + timedelta(minutes=7))
        self.assertEqual(
            next_due_utc(END + timedelta(minutes=8), last_attempted_hour=END),
            END + HOUR + timedelta(minutes=7))
        with self.assertRaises(ValueError):
            next_due_utc(datetime(2026, 9, 29, 18, 7))


class CloudCycleTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)/"isolated-cloud-forward"
        self.root.mkdir(mode=0o700)

    def tick(self, closed, *, factory=None):
        now = closed + timedelta(minutes=7)
        if factory is None:
            source = FakeBars(synthetic(closed))
            factory = lambda: source
        else:
            source = None
        value = cloud_cycle_once(
            root=self.root, now=now, provider_factory=factory,
            after_capture_now=lambda: now+timedelta(minutes=1))
        return value, source

    def test_volume_must_be_precreated_private(self):
        missing = self.root/"missing"
        with self.assertRaises(ValueError):
            _private_volume(missing)
        self.assertFalse(missing.exists())
        self.root.chmod(0o755)
        with self.assertRaises(PermissionError):
            _private_volume(self.root)
        self.root.chmod(0o700)

    def test_zero_bootstrap_then_1_and_2_prospective_with_immutable_shadow_receipts(self):
        first, initial_source = self.tick(END)
        self.assertEqual(initial_source.requests, 1)
        self.assertEqual(first["status"],
                         "HISTORY_BOOTSTRAPPED_NO_RETROSPECTIVE_SHADOW")
        self.assertEqual(first["prospective_observations_verified"], 0)
        self.assertFalse((self.root/"cloud-shadow-receipts").exists())
        self.assertEqual(first["broker_order_submission"], "DISABLED")
        second, second_source = self.tick(END + HOUR)
        self.assertEqual(second_source.requests, 1)
        self.assertEqual(second["status"],
                         "ONE_PROSPECTIVE_OBSERVATION_AND_SHADOW_ARCHIVED")
        self.assertEqual(second["prospective_observations_verified"], 1)
        self.assertEqual(second["shadow_signal_count"], 3)
        report1 = self.root/"cloud-shadow-receipts"/"shadow-20260929T1900Z.json"
        self.assertTrue(report1.is_file())
        self.assertEqual(report1.stat().st_mode & 0o777, 0o600)
        saved = json.loads(report1.read_text())
        self.assertEqual(saved["kind"],
                         "CLOUD_SHA_BOUND_SHADOW_EVALUATION_NO_ORDER")
        self.assertEqual(saved["prospective_observations_verified"], 1)
        self.assertTrue(all(row["broker_order_submission"] == "DISABLED"
                            for row in saved["research_decisions"]))
        self.assertFalse(saved["strategy_promoted"])

        before = captured_files(self.root)
        duplicate = cloud_cycle_once(
            root=self.root, now=END + HOUR + timedelta(minutes=12),
            provider_factory=lambda: self.fail("duplicate must never request credentials"))
        self.assertEqual(duplicate["status"], "SAFE_NO_NEW_OBSERVATION")
        for path, digest in before.items():
            if path.endswith(".lock"):
                continue  # current lock PID may be refreshed on a no-op tick
            p = self.root/path
            self.assertTrue(p.exists())
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), digest)
        third, third_source = self.tick(END + 2 * HOUR)
        self.assertEqual(third_source.requests, 1)
        self.assertEqual(third["prospective_observations_verified"], 2)
        report2 = self.root/"cloud-shadow-receipts"/"shadow-20260929T2000Z.json"
        self.assertTrue(report2.is_file())
        self.assertEqual(hashlib.sha256(report1.read_bytes()).hexdigest(),
                         before["cloud-shadow-receipts/shadow-20260929T1900Z.json"])
        self.assertEqual(len(list((self.root/"cloud-shadow-receipts").glob("*.json"))), 2)
        status = cloud_status(root=self.root)
        self.assertEqual(status["status"], "READ_ONLY_STATUS_AVAILABLE")
        self.assertEqual(status["verified_collector"]["prospective_observations_verified"], 2)

    def test_gap_starts_independent_bootstrap_not_synthetic_catchup(self):
        self.tick(END)
        self.tick(END + HOUR)
        old = self.root/"observations-auto-20260929T1800Z.sqlite3"
        old_digest = hashlib.sha256(old.read_bytes()).hexdigest()
        gap, provider = self.tick(END + 3*HOUR)
        self.assertEqual(provider.requests, 1)
        self.assertEqual(gap["collector_decision"], "NEW_AUTO_SEGMENT_AFTER_MISSED_HOUR")
        self.assertEqual(gap["status"], "HISTORY_BOOTSTRAPPED_NO_RETROSPECTIVE_SHADOW")
        self.assertEqual(gap["prospective_observations_verified"], 0)
        self.assertEqual(hashlib.sha256(old.read_bytes()).hexdigest(), old_digest)
        self.assertEqual(len(list((self.root/"cloud-shadow-receipts").glob("*.json"))), 1)

    def test_transport_error_latches_durable_pause_and_does_not_retry(self):
        def fail():
            raise TimeoutError("synthetic private fixture data")
        out, _ = self.tick(END, factory=fail)
        self.assertEqual(out["status"], "PAUSED_OPERATOR_REVIEW_REQUIRED")
        self.assertEqual(out["collector_decision"], "HALT_PRESERVE_ALL_ORIGINAL_EVIDENCE")
        marker = self.root/".cloud-collector-paused.json"
        self.assertTrue(marker.is_file())
        self.assertEqual(marker.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("synthetic private fixture data", json.dumps(out))
        blocked, _ = self.tick(END + HOUR, factory=lambda: self.fail(
            "never access provider while paused"))
        self.assertEqual(blocked["reason_code"], "DURABLE_FAIL_CLOSED_PAUSE_PRESENT")
        self.assertTrue(cloud_status(root=self.root)["durably_paused"])
        before = captured_files(self.root)
        blocked_again, _ = self.tick(END + 2*HOUR, factory=lambda: self.fail(
            "must remain paused even after new hourly close"))
        self.assertEqual(blocked_again["status"], "PAUSED_OPERATOR_REVIEW_REQUIRED")
        self.assertEqual(before, captured_files(self.root))

    def test_shadow_tamper_latches_pause_preserving_all_real_captures(self):
        self.tick(END)
        out, _ = self.tick(END + HOUR)
        self.assertEqual(out["status"], "ONE_PROSPECTIVE_OBSERVATION_AND_SHADOW_ARCHIVED")
        captured = next((self.root/"captures").glob("*end_20260929T1900Z.csv"))
        captured.write_bytes(captured.read_bytes() + b"tamper")
        # A subsequent valid collector tick performs the old archive audit
        # before asking provider for any new capture, and fails closed.
        failed, _ = self.tick(
            END + 2*HOUR, factory=lambda: self.fail("tampered archive must block request"))
        self.assertEqual(failed["status"], "PAUSED_OPERATOR_REVIEW_REQUIRED")
        self.assertTrue((self.root/".cloud-collector-paused.json").exists())
        self.assertIn(b"tamper", captured.read_bytes())

    def test_shadow_receipt_conflict_never_overwrites_and_latches_pause(self):
        self.tick(END)
        self.tick(END + HOUR)
        report = inspect_latest_shadow_signal(forward_root=self.root)
        result = _write_shadow_receipt(self.root, report)
        self.assertEqual(result, "ALREADY_ARCHIVED_IDENTICAL")
        existing = self.root/"cloud-shadow-receipts"/"shadow-20260929T1900Z.json"
        existing.write_text('{"manipulated":true}\n')
        with self.assertRaises(ValueError):
            _write_shadow_receipt(self.root, report)
        self.assertEqual(existing.read_text(), '{"manipulated":true}\n')


if __name__ == "__main__":
    unittest.main()

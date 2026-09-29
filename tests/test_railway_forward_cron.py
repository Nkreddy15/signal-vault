"""Synthetic, offline-only Railway cron adapter acceptance.

No Railway account, Docker daemon, real provider, secrets or order POST.
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

from signal_vault.market_data import Bar
from signal_vault.railway_forward_cron import (
    KEY_VARIABLE, SECRET_VARIABLE, RAILWAY_MOUNT_VARIABLE,
    configured_railway_volume, railway_data_credentials,
    railway_once, railway_preflight,
)

END = datetime(2026, 9, 29, 18, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)


def fixture(closed):
    first = closed - 72 * HOUR
    rows = []
    for n in range(72):
        date = first + n * HOUR
        k = int((date - (END - 72 * HOUR)).total_seconds() / 3600)
        px = Decimal("80000") + Decimal(k * 12)
        rows.append(Bar(date, px, px + Decimal("10"), px - Decimal("10"),
                        px, Decimal("5"), "alpaca_crypto_us"))
    return tuple(rows)


class FakeGetOnly:
    def __init__(self, items):
        self.items = items
        self.calls = 0

    def fetch(self, *, start, end, as_of):
        self.calls += 1
        return self.items


def hashes(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*") if p.is_file()
    }


class RailwayAdapterTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "railway-volume"
        self.root.mkdir(mode=0o700)
        self.env = {
            RAILWAY_MOUNT_VARIABLE: str(self.root),
            KEY_VARIABLE: "SYNTHETIC_DATA_KEY",
            SECRET_VARIABLE: "SYNTHETIC_DATA_SECRET",
        }

    def test_no_volume_provenance_means_no_ephemeral_disk_fallback_or_capture(self):
        missing = self.root.parent / "not-a-volume"
        source = FakeGetOnly(fixture(END))
        without_mount = {k:v for k,v in self.env.items()
                         if k != RAILWAY_MOUNT_VARIABLE}
        r = railway_once(
            now=END + timedelta(minutes=7),
            environ=without_mount,
            expected_root=missing,
            provider_factory=lambda: source)
        self.assertEqual(r["reason_code"], "RAILWAY_PERSISTENT_VOLUME_NOT_READY")
        self.assertFalse(missing.exists())
        self.assertEqual(source.calls, 0)
        self.assertEqual(r["broker_order_submission"], "DISABLED")
        self.assertEqual(hashes(self.root), {})

    def test_secret_unset_blocks_without_creation_or_network(self):
        source = FakeGetOnly(fixture(END))
        env = {RAILWAY_MOUNT_VARIABLE: str(self.root)}
        result = railway_once(
            now=END + timedelta(minutes=7), environ=env,
            expected_root=self.root, provider_factory=lambda: source)
        self.assertEqual(
            result["reason_code"], "DEDICATED_DATA_VARIABLE_NAMES_NOT_READY_OR_UNSAFE_ENV")
        self.assertEqual(source.calls, 0)
        self.assertEqual(hashes(self.root), {})

    def test_no_generic_live_paper_order_credential_fallback(self):
        for forbidden in ("ALPACA_API_KEY_ID", "ALPACA_LIVE_KEY_ID",
                          "APCA_API_SECRET_KEY", "ALPACA_PAPER_KEY_ID",
                          "SIGNAL_VAULT_ENABLE_PAPER_ORDERS"):
            with self.subTest(forbidden=forbidden):
                env = {**self.env, forbidden: "NEVER"}
                with self.assertRaises(ValueError):
                    railway_data_credentials(environ=env)
                read = railway_once(
                    now=END + timedelta(minutes=7),
                    environ=env, expected_root=self.root,
                    provider_factory=lambda: self.fail("provider must not be called"))
                self.assertEqual(
                    read["reason_code"],
                    "DEDICATED_DATA_VARIABLE_NAMES_NOT_READY_OR_UNSAFE_ENV")
                self.assertEqual(hashes(self.root), {})

    def test_credentials_validate_without_exposing_their_values(self):
        c = railway_data_credentials(environ=self.env)
        self.assertEqual(c.key_id, "SYNTHETIC_DATA_KEY")
        self.assertEqual(c.secret_key, "SYNTHETIC_DATA_SECRET")
        self.assertNotIn("SYNTHETIC", repr(c))
        pre = railway_preflight(environ=self.env, expected_root=self.root)
        self.assertEqual(pre["status"], "RAILWAY_LOCAL_PREFLIGHT_PASS_NO_NETWORK")
        self.assertEqual(pre["network_requests"], "NONE")
        self.assertNotIn("SYNTHETIC", json.dumps(pre))
        bad = railway_preflight(
            environ={**self.env, KEY_VARIABLE: "SYNTHETIC_DATA_KEY\n"},
            expected_root=self.root)
        self.assertEqual(bad["status"], "BLOCKED")
        self.assertNotIn("SYNTHETIC", json.dumps(bad))

    def test_mount_symlink_or_public_permissions_fail_closed(self):
        link = self.root.parent/"symlink"
        link.symlink_to(self.root)
        with self.assertRaises(ValueError):
            configured_railway_volume(environ={
                **self.env, RAILWAY_MOUNT_VARIABLE: str(link)},
                expected_root=link)
        self.root.chmod(0o755)
        with self.assertRaises(PermissionError):
            configured_railway_volume(
                environ=self.env, expected_root=self.root,
                allow_owner_permission_repair=False)
        # Repair only when EUID truly 0; ordinary callers may not elevate.
        with patch("signal_vault.railway_forward_cron.os.geteuid", return_value=10001):
            with self.assertRaises(PermissionError):
                configured_railway_volume(
                    environ=self.env, expected_root=self.root,
                    allow_owner_permission_repair=True)
        self.root.chmod(0o700)

    def test_bootstrap_then_two_prospective_shadow_receipts_with_fake_get(self):
        def tick(closed):
            source = FakeGetOnly(fixture(closed))
            at = closed + timedelta(minutes=7)
            result = railway_once(
                now=at, environ=self.env, expected_root=self.root,
                provider_factory=lambda: source,
                after_capture_now=lambda: at + timedelta(minutes=1))
            self.assertEqual(source.calls, 1)
            self.assertEqual(result["broker_order_submission"], "DISABLED")
            self.assertEqual(result["automatic_paper_trading"], "DISABLED")
            self.assertNotIn("SYNTHETIC", json.dumps(result))
            return result

        first = tick(END)
        self.assertEqual(first["status"],
                         "HISTORY_BOOTSTRAPPED_NO_RETROSPECTIVE_SHADOW")
        self.assertEqual(first["prospective_observations_verified"], 0)
        second = tick(END + HOUR)
        self.assertEqual(second["status"],
                         "ONE_PROSPECTIVE_OBSERVATION_AND_SHADOW_ARCHIVED")
        self.assertEqual(second["prospective_observations_verified"], 1)
        self.assertEqual(second["shadow_signal_count"], 3)
        rec1 = self.root/"cloud-shadow-receipts"/"shadow-20260929T1900Z.json"
        self.assertTrue(rec1.is_file())
        first_sha = hashlib.sha256(rec1.read_bytes()).hexdigest()
        third = tick(END + 2*HOUR)
        self.assertEqual(third["prospective_observations_verified"], 2)
        self.assertEqual(hashlib.sha256(rec1.read_bytes()).hexdigest(), first_sha)
        rec2 = self.root/"cloud-shadow-receipts"/"shadow-20260929T2000Z.json"
        self.assertTrue(rec2.is_file())
        self.assertEqual(json.loads(rec2.read_text())["broker_order_submission"],
                         "DISABLED")

    def test_worker_hour_timing_blocks_early_unplanned_data_get(self):
        source = FakeGetOnly(fixture(END))
        # At :01, inherited original collector exits without credentials/network.
        result = railway_once(
            now=END + timedelta(minutes=1),
            environ=self.env, expected_root=self.root,
            provider_factory=lambda: source)
        self.assertEqual(result["status"], "SAFE_NO_NEW_OBSERVATION")
        self.assertEqual(source.calls, 0)

    def test_provider_failure_pauses_volume_and_next_run_never_retries(self):
        at = END + timedelta(minutes=7)
        def fail():
            raise RuntimeError("NEVER_SHOW_PRIVATE_PROVIDER_ERROR")
        first = railway_once(
            now=at, environ=self.env, expected_root=self.root,
            provider_factory=fail,
            after_capture_now=lambda: at+timedelta(minutes=1))
        self.assertEqual(first["status"], "PAUSED_OPERATOR_REVIEW_REQUIRED")
        self.assertNotIn("NEVER_SHOW_PRIVATE", json.dumps(first))
        self.assertTrue((self.root/".cloud-collector-paused.json").is_file())
        second = railway_once(
            now=at+HOUR, environ=self.env, expected_root=self.root,
            provider_factory=lambda: self.fail("no retry after durable pause"))
        self.assertEqual(second["status"], "PAUSED_OPERATOR_REVIEW_REQUIRED")
        self.assertEqual(second["reason_code"], "DURABLE_FAIL_CLOSED_PAUSE_PRESENT")


if __name__ == "__main__":
    unittest.main()

"""Offline fake-provider acceptance for the first real prospective shadow signal.

Only disposable owner-local-shaped archives and synthetic bars. Never accesses
Alpaca, credentials, an actual Mac launch job, an account or an order endpoint.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.market_data import Bar
from signal_vault.shadow_signal_snapshot import inspect_latest_shadow_signal
from signal_vault.unattended_forward_cycle import run_unattended_once, status_unattended

END = datetime(2026, 9, 29, 18, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)


def synthetic(closed):
    start = closed - 72 * HOUR
    rows = []
    for i in range(72):
        at = start + i * HOUR
        k = int((at - (END - 72 * HOUR)).total_seconds() / 3600)
        close = Decimal("70000") + Decimal(k) * Decimal("15")
        rows.append(Bar(at, close, close + 10, close - 10, close,
                        Decimal("10"), "alpaca_crypto_us"))
    return tuple(rows)


class FakeMarketData:
    def __init__(self, bars):
        self.bars = bars
        self.reads = 0

    def fetch(self, *, start, end, as_of):
        self.reads += 1
        return self.bars


def file_hashes(root):
    return {
        str(item.relative_to(root)): hashlib.sha256(item.read_bytes()).hexdigest()
        for item in root.rglob("*") if item.is_file()
    }


class LatestProspectiveShadowTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name) / "forward"
        self.root.mkdir(mode=0o700)

    def tick(self, closed):
        source = FakeMarketData(synthetic(closed))
        stamp = closed + timedelta(minutes=7)
        output = run_unattended_once(
            root=self.root, now=stamp,
            provider_factory=lambda: source,
            after_capture_now=lambda: stamp + timedelta(minutes=1),
        )
        self.assertEqual(source.reads, 1)
        return output

    def test_bootstrap_not_mislabeled_as_a_prospective_shadow_signal(self):
        self.assertEqual(self.tick(END)["decision"], "FIRST_AUTO_SEGMENT_BOOTSTRAPPED")
        before = file_hashes(self.root)
        report = inspect_latest_shadow_signal(forward_root=self.root)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["reason_code"], "BOOTSTRAP_ONLY_NOT_PROSPECTIVE")
        self.assertEqual(report["prospective_observations_verified"], 0)
        self.assertEqual(report["broker_order_submission"], "DISABLED")
        self.assertEqual(before, file_hashes(self.root))

    def test_first_forward_candle_produces_three_distinct_archived_research_signals(self):
        self.tick(END)
        self.assertEqual(self.tick(END + HOUR)["decision"],
                         "ONE_NEW_PROSPECTIVE_CANDLE_RECORDED")
        status = status_unattended(root=self.root)
        self.assertEqual(status["prospective_observations_verified"], 1)
        original_files = file_hashes(self.root)
        result = inspect_latest_shadow_signal(forward_root=self.root)
        self.assertEqual(result["status"],
                         "AUDITED_ONE_CANDLE_SHADOW_SIGNALS_RESEARCH_ONLY")
        self.assertEqual(result["reason_code"], "NONE")
        self.assertEqual(result["prospective_observations_verified"], 1)
        self.assertEqual(result["evidence"]["bar_started_utc"], END.isoformat())
        self.assertEqual(result["evidence"]["bar_closed_utc"],
                         (END + HOUR).isoformat())
        self.assertEqual(result["evidence"]["research_history_hours"], 72)
        self.assertEqual(len(result["evidence"]["capture_sha256"]), 64)
        self.assertEqual(result["evidence"]["read_only_archive_audit"],
                         "PASS_INTERNAL_CONSISTENCY_ONLY")
        signals = result["research_decisions"]
        self.assertEqual(len(signals), 3)
        self.assertEqual(len(set(s["strategy_version"] for s in signals)), 3)
        self.assertTrue(all(
            s["broker_order_submission"] == "DISABLED"
            and s["observed_signal"] in ("buy", "sell", "hold")
            for s in signals))
        self.assertFalse(result["strategy_promoted"])
        self.assertEqual(result["market_data_requests"], "NONE")
        self.assertEqual(result["keychain_access"], "NONE")
        self.assertEqual(result["paper_account_access"], "NONE")
        self.assertFalse(result["collector_modified"])
        self.assertFalse(result["journal_modified"])
        self.assertEqual(original_files, file_hashes(self.root))

    def test_second_consecutive_candle_uses_only_latest_prospective_close(self):
        self.tick(END)
        self.tick(END + HOUR)
        self.tick(END + 2 * HOUR)
        result = inspect_latest_shadow_signal(forward_root=self.root)
        self.assertEqual(result["status"],
                         "AUDITED_ONE_CANDLE_SHADOW_SIGNALS_RESEARCH_ONLY")
        self.assertEqual(result["prospective_observations_verified"], 2)
        self.assertEqual(result["evidence"]["bar_started_utc"],
                         (END + HOUR).isoformat())
        self.assertEqual(result["evidence"]["bar_closed_utc"],
                         (END + 2 * HOUR).isoformat())
        self.assertTrue(all(
            row["broker_order_submission"] == "DISABLED"
            for row in result["research_decisions"]))

    def test_tampered_capture_fails_closed_without_modifying_archive(self):
        self.tick(END)
        self.tick(END + HOUR)
        latest = self.root / "captures" / "btcusd_72h_end_20260929T1900Z.csv"
        latest.write_bytes(latest.read_bytes() + b"\nTAMPERED\n")
        original = file_hashes(self.root)
        report = inspect_latest_shadow_signal(forward_root=self.root)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["reason_code"],
                         "ARCHIVED_AUTOMATIC_EVIDENCE_OR_SIGNAL_AUDIT_FAILED")
        self.assertEqual(report["failure_class"], "ValueError")
        self.assertNotIn("research_decisions", report)
        self.assertEqual(original, file_hashes(self.root))

    def test_collector_updates_midread_block_without_partial_signals(self):
        self.tick(END)
        self.tick(END + HOUR)
        first = status_unattended(root=self.root)
        calls = []

        def changing(**_):
            calls.append(1)
            if len(calls) == 1:
                return first
            return {**first, "prospective_observations_verified": 2}

        result = inspect_latest_shadow_signal(
            forward_root=self.root, collector_reader=changing)
        self.assertEqual(result["reason_code"],
                         "ARCHIVE_ADVANCED_DURING_READ_RETRY_LATER")
        self.assertNotIn("research_decisions", result)
        self.assertEqual(len(calls), 2)

    def test_missing_or_invalid_fake_pointer_never_creates_storage(self):
        empty = Path(self.root.parent) / "not-created"
        report = inspect_latest_shadow_signal(forward_root=empty)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(empty.exists())
        self.assertNotIn("research_decisions", report)

        self.tick(END)
        self.tick(END + HOUR)
        valid = status_unattended(root=self.root)
        modified = {**valid, "active_auto_journal": "../outside.sqlite3"}
        report = inspect_latest_shadow_signal(
            forward_root=self.root, collector_reader=lambda **_: modified)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["reason_code"],
                         "ARCHIVED_AUTOMATIC_EVIDENCE_OR_SIGNAL_AUDIT_FAILED")

    def test_invalid_spread_is_rejected_before_touching_any_archive(self):
        def fail(**_):
            self.fail("cost input should block before archive read")
        report = inspect_latest_shadow_signal(
            forward_root=self.root,
            assumed_spread_bps=Decimal("NaN"),
            collector_reader=fail)
        self.assertEqual(report["reason_code"], "INVALID_EXPLICIT_COST_SCENARIO")
        self.assertEqual(report["market_data_requests"], "NONE")

    def test_collector_halt_does_not_emit_signal(self):
        self.tick(END)
        self.tick(END + HOUR)
        original = status_unattended(root=self.root)
        halted = {**original,
                  "latest_tick": {"decision": "HALT_PRESERVE_ALL_ORIGINAL_EVIDENCE"}}
        r = inspect_latest_shadow_signal(
            forward_root=self.root, collector_reader=lambda **_: halted)
        self.assertEqual(r["reason_code"], "HALTED_COLLECTOR_PRESERVE_EVIDENCE")
        self.assertNotIn("research_decisions", r)


if __name__ == "__main__":
    unittest.main()

"""Forward incident summary is classification-only: no repairs, keys or orders."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from signal_vault.forward_incident_report import forward_incident_report
from signal_vault.railway_btc_first_dual_cron import BASENAME


def dual(status="BTC_AND_SIX_CRYPTO_CURRENTLY_ALIGNED",*,reason="NONE",
         btc=8,hours=1,scored=0,source_ready=False,scored_ready=False):
    return {
        "status":status,
        "reason_code":reason,
        "btc_prospective_observations_verified":btc,
        "six_crypto_current_segment_independent_prospective_hours":hours,
        "six_crypto_current_segment_prospective_asset_bar_count":6*hours,
        "six_crypto_fully_observed_precommitted_decision_intervals":scored,
        "six_crypto_source_168_hour_collection_ready":source_ready,
        "six_crypto_fully_scored_168_decision_outcomes_ready":scored_ready,
        "broker_order_submission":"DISABLED",
    }


def storage(status="CURRENT_STORAGE_GUARDS_HEALTHY"):
    return {
        "status":status,
        "sidecar_bytes":12345,
        "filesystem_available_bytes":400_000_000,
        "btc_reserved_free_bytes":128*1024*1024,
        "automatic_pruning":"DISABLED",
        "broker_order_submission":"DISABLED",
    }


class OfflineForwardIncidentReportTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.btc=Path(tmp.name)/"forward"
        self.btc.mkdir(mode=0o700)
        self.side=self.btc/BASENAME

    def report(self,d,s):
        with patch(
            "signal_vault.forward_incident_report.dual_forward_integrity_status",
            return_value=d,
        ) as dual_mock, patch(
            "signal_vault.forward_incident_report.sidecar_storage_audit",
            return_value=s,
        ) as storage_mock:
            out=forward_incident_report(
                btc_root=self.btc,sidecar_root=self.side)
        dual_mock.assert_called_once_with(
            btc_root=self.btc,sidecar_root=self.side)
        storage_mock.assert_called_once_with(
            btc_root=self.btc,sidecar_root=self.side)
        return out

    def test_current_aligned_accumulation_is_info_and_requires_no_owner_action(self):
        out=self.report(dual(),storage())
        self.assertEqual(out["status"],"HEALTHY_FORWARD_EVIDENCE_ACCUMULATING")
        self.assertEqual(out["severity"],"info")
        self.assertEqual(out["btc_prospective_observations_verified"],8)
        self.assertEqual(out["six_crypto_current_segment_independent_prospective_hours"],1)
        self.assertEqual(out["six_crypto_current_segment_prospective_asset_bars"],6)
        self.assertFalse(out["engineering_review_required"])
        self.assertFalse(out["owner_access_action_required_by_this_report"])
        self.assertEqual(out["network_requests"],"NONE")
        self.assertEqual(out["credentials_accessed"],"NONE")
        self.assertFalse(out["files_modified"])
        self.assertEqual(out["broker_order_submission"],"DISABLED")

    def test_168_source_milestone_is_not_168_scored_outcome_claim(self):
        out=self.report(
            dual(
                "SIX_CRYPTO_168_SOURCE_HOURS_READY_WAITING_ONE_MORE_OUTCOME",
                btc=175,hours=168,scored=167,source_ready=True),
            storage())
        self.assertEqual(out["status"],"MILESTONE_168_SOURCE_HOURS_AVAILABLE")
        self.assertTrue(out["six_crypto_source_168_hour_collection_ready"])
        self.assertFalse(out["six_crypto_fully_scored_168_decision_outcomes_ready"])
        self.assertEqual(out["six_crypto_fully_observed_precommitted_decision_intervals"],167)
        self.assertFalse(out["strategy_promoted"])
        self.assertFalse(out["future_edge_established"])

    def test_169_source_hours_can_report_168_scored_milestone_without_strategy_promotion(self):
        out=self.report(
            dual(
                "SIX_CRYPTO_168_PRECOMMITTED_OUTCOMES_READY",
                btc=176,hours=169,scored=168,
                source_ready=True,scored_ready=True),
            storage())
        self.assertEqual(
            out["status"],"MILESTONE_168_PRECOMMITTED_OUTCOMES_AVAILABLE")
        self.assertEqual(out["severity"],"info")
        self.assertTrue(out["six_crypto_fully_scored_168_decision_outcomes_ready"])
        self.assertFalse(out["strategy_promoted"])
        self.assertEqual(out["automatic_paper_trading"],"DISABLED")

    def test_sidecar_lag_or_capacity_warning_requires_engineering_review_not_owner_action(self):
        lag=self.report(
            dual("BTC_HEALTHY_SIX_CRYPTO_BEHIND",
                 reason="SIX_CRYPTO_MISSED_OR_FAILED_LATEST_BTC_FIRST_TICK"),
            storage())
        self.assertEqual(lag["severity"],"warning")
        self.assertTrue(lag["engineering_review_required"])
        self.assertFalse(lag["owner_access_action_required_by_this_report"])
        capacity=self.report(
            dual(),
            storage("CAPACITY_PROJECTION_WARNING_PRESERVE_ALL_EVIDENCE"))
        self.assertEqual(capacity["severity"],"warning")
        self.assertIn(
            "SIX_MARKET_CAPACITY_PROJECTION_WARNING",
            capacity["reason_codes"])

    def test_BTC_pause_or_blocked_integrity_is_critical_but_does_not_auto_repair(self):
        for state,reason in (
            ("BTC_PAUSED_SIDE_EVIDENCE_PRESERVED","BTC_DURABLE_PAUSE_PRESENT"),
            ("BLOCKED","SIX_CRYPTO_SOURCE_ARCHIVE_SCORECARD_COUNTS_DIVERGE"),
        ):
            with self.subTest(state=state):
                out=self.report(dual(state,reason=reason),storage())
                self.assertEqual(out["status"],"BLOCKED_PRESERVE_EVIDENCE")
                self.assertEqual(out["severity"],"critical")
                self.assertTrue(out["engineering_review_required"])
                self.assertEqual(out["automatic_repair_of_source_evidence"],"DISABLED")
                self.assertEqual(out["automatic_pruning"],"DISABLED")
                self.assertEqual(out["broker_order_submission"],"DISABLED")

    def test_hard_storage_guard_preserves_BTC_and_never_requests_paid_resource(self):
        out=self.report(
            dual(),
            storage("HARD_GUARD_WOULD_SKIP_NEXT_SIDECAR_TICK"))
        self.assertEqual(out["status"],"WARNING_PRESERVE_BTC_STORAGE_RESERVE")
        self.assertEqual(out["severity"],"warning")
        self.assertFalse(out["owner_access_action_required_by_this_report"])
        self.assertEqual(out["automatic_pruning"],"DISABLED")


if __name__=="__main__":
    unittest.main()

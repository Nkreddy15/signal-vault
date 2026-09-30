"""Operator report is read-only and never turns an alert into a mutation."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from signal_vault.forward_operator_report import forward_operator_report
from signal_vault.railway_btc_first_dual_cron import BASENAME


def integrity(status,*,btc=8,hours=1,ready=False):
    return {
        "status":status,
        "btc_prospective_observations_verified":btc,
        "six_crypto_current_segment_independent_prospective_hours":hours,
        "six_crypto_ready_for_168_hour_audit":ready,
        "network_requests":"NONE",
        "broker_order_submission":"DISABLED",
    }


def storage(status="CURRENT_STORAGE_GUARDS_HEALTHY"):
    return {
        "status":status,
        "automatic_pruning":"DISABLED",
        "evidence_deletion":"DISABLED",
        "network_requests":"NONE",
        "broker_order_submission":"DISABLED",
    }


def score(status="PROSPECTIVE_SHADOW_OUTCOMES_ACCUMULATING",*,scored=1,ready=False):
    return {
        "status":status,
        "fully_observed_precommitted_decision_intervals":scored,
        "full_168_precommitted_decision_outcomes_ready":ready,
        "strategy_promoted":False,
        "network_requests":"NONE",
        "broker_order_submission":"DISABLED",
    }


class ForwardOperatorReportTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.btc=Path(tmp.name)/"forward"
        self.btc.mkdir(mode=0o700)
        self.side=self.btc/BASENAME
        self.side.mkdir(mode=0o700)

    def report(self,i,s=storage(),q=score()):
        with patch(
            "signal_vault.forward_operator_report.dual_forward_integrity_status",
            return_value=i),patch(
            "signal_vault.forward_operator_report.sidecar_storage_audit",
            return_value=s),patch(
            "signal_vault.forward_operator_report.prospective_shadow_scorecard",
            return_value=q):
            return forward_operator_report(
                btc_root=self.btc,sidecar_root=self.side)

    def assert_never_acts(self,result):
        self.assertFalse(result["report_itself_modified_evidence"])
        self.assertEqual(result["network_requests"],"NONE")
        self.assertEqual(result["credentials_accessed"],"NONE")
        self.assertEqual(result["broker_order_submission"],"DISABLED")
        self.assertEqual(result["automatic_paper_trading"],"DISABLED")
        self.assertEqual(result["live_trading"],"UNAVAILABLE")
        self.assertIn("DELETE_OR_PRUNE_EVIDENCE",
                      result["automatic_actions_forbidden"])
        self.assertIn("ENABLE_PAPER_ORDER_SUBMISSION",
                      result["automatic_actions_forbidden"])
        self.assertIn("CREATE_PAID_RESOURCES",
                      result["automatic_actions_forbidden"])

    def test_aligned_collection_is_info_no_mutation(self):
        result=self.report(
            integrity("BTC_AND_SIX_CRYPTO_CURRENTLY_ALIGNED",btc=8,hours=1))
        self.assertEqual(result["severity"],"INFO")
        self.assertEqual(result["state"],"HEALTHY_ALIGNED_FORWARD_COLLECTION")
        self.assertEqual(result["btc_prospective_observations_verified"],8)
        self.assertEqual(
            result["six_crypto_current_segment_prospective_source_hours"],1)
        self.assertEqual(
            result["six_crypto_fully_observed_precommitted_decision_intervals"],1)
        self.assert_never_acts(result)

    def test_initial_baseline_stage_is_info_and_waits(self):
        result=self.report(
            integrity("BTC_HEALTHY_SIX_CRYPTO_BASELINE_ONLY",hours=0),
            q=score(
                "HISTORICAL_72H_BASELINE_ONLY_ZERO_PROSPECTIVE",
                scored=0))
        self.assertEqual(result["severity"],"INFO")
        self.assertEqual(result["state"],"HEALTHY_EARLY_COLLECTION_STAGE")
        self.assertIn("WAIT",result["operator_response"])
        self.assert_never_acts(result)

    def test_one_hour_lag_is_warning_not_backfill_instruction(self):
        result=self.report(
            integrity("BTC_HEALTHY_SIX_CRYPTO_BEHIND",hours=4),
            q=score(scored=3))
        self.assertEqual(result["severity"],"WARNING")
        self.assertEqual(result["state"],"SIX_CRYPTO_BEHIND_BTC_FIRST_STREAM")
        self.assertIn("SIDECAR_LAG",result["reason_codes"])
        self.assertNotIn("BACKFILL",result["operator_response"])
        self.assertIn("BACKFILL_MISSED_PROSPECTIVE_HOURS",
                      result["automatic_actions_forbidden"])
        self.assert_never_acts(result)

    def test_capacity_projection_warning_never_spends_or_prunes(self):
        result=self.report(
            integrity("BTC_AND_SIX_CRYPTO_CURRENTLY_ALIGNED",hours=10),
            s=storage("CAPACITY_PROJECTION_WARNING_PRESERVE_ALL_EVIDENCE"),
            q=score(scored=9))
        self.assertEqual(result["severity"],"WARNING")
        self.assertEqual(result["state"],"CAPACITY_PROJECTION_WARNING")
        self.assertIn("NO_AUTOMATIC_SPEND_OR_DELETE",
                      result["operator_response"])
        self.assert_never_acts(result)

    def test_hard_storage_guard_requires_review_and_preserves_evidence(self):
        result=self.report(
            integrity("BTC_AND_SIX_CRYPTO_CURRENTLY_ALIGNED",hours=20),
            s=storage("HARD_GUARD_WOULD_SKIP_NEXT_SIDECAR_TICK"),
            q=score(scored=19))
        self.assertEqual(result["severity"],"HALT_REVIEW")
        self.assertEqual(result["state"],"STORAGE_HARD_GUARD_REQUIRES_REVIEW")
        self.assertIn("STORAGE_HARD_GUARD",result["reason_codes"])
        self.assertIn("NO_AUTOMATIC_PRUNING",result["operator_response"])
        self.assert_never_acts(result)

    def test_BTC_pause_or_integrity_failure_is_halt_review(self):
        for status in ("BTC_PAUSED_SIDE_EVIDENCE_PRESERVED","BLOCKED"):
            with self.subTest(status=status):
                result=self.report(integrity(status))
                self.assertEqual(result["severity"],"HALT_REVIEW")
                self.assertEqual(
                    result["state"],
                    "EVIDENCE_INTEGRITY_OR_BTC_PAUSE_REQUIRES_REVIEW")
                self.assertIn("INTEGRITY_OR_PAUSE",result["reason_codes"])
                self.assert_never_acts(result)

    def test_168_source_vs_168_scored_are_reported_separately(self):
        result=self.report(
            integrity(
                "SIX_CRYPTO_168_HOUR_CONTIGUOUS_EVIDENCE_READY",
                btc=175,hours=168,ready=True),
            q=score(scored=167,ready=False))
        self.assertTrue(result["six_crypto_source_168_hour_collection_ready"])
        self.assertFalse(result["six_crypto_168_scored_decisions_ready"])
        self.assertEqual(result["severity"],"INFO")
        self.assert_never_acts(result)

    def test_component_exception_is_captured_as_halt_without_recovery(self):
        with patch(
            "signal_vault.forward_operator_report.dual_forward_integrity_status",
            side_effect=ValueError("corrupt source")),patch(
            "signal_vault.forward_operator_report.sidecar_storage_audit",
            return_value=storage()),patch(
            "signal_vault.forward_operator_report.prospective_shadow_scorecard",
            return_value=score()):
            result=forward_operator_report(
                btc_root=self.btc,sidecar_root=self.side)
        self.assertEqual(result["severity"],"HALT_REVIEW")
        self.assertEqual(result["components"]["integrity"]["failure_class"],
                         "ValueError")
        self.assert_never_acts(result)

    def test_absent_sidecar_does_not_call_scorecard_or_create_path(self):
        self.side.rmdir()
        with patch(
            "signal_vault.forward_operator_report.dual_forward_integrity_status",
            return_value=integrity(
                "BTC_ONLY_HEALTHY_WAITING_FOR_FIRST_SIX_CRYPTO_TICK",
                hours=0)),patch(
            "signal_vault.forward_operator_report.sidecar_storage_audit",
            return_value=storage("SIDECAR_NOT_YET_CREATED")),patch(
            "signal_vault.forward_operator_report.prospective_shadow_scorecard"
        ) as q:
            result=forward_operator_report(
                btc_root=self.btc,sidecar_root=self.side)
        q.assert_not_called()
        self.assertFalse(self.side.exists())
        self.assertEqual(result["severity"],"INFO")
        self.assertEqual(result["state"],"HEALTHY_EARLY_COLLECTION_STAGE")
        self.assert_never_acts(result)


if __name__=="__main__":
    unittest.main()

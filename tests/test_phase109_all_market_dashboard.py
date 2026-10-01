import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from signal_vault.all_market_dashboard import (
    KIND,
    build_dashboard_snapshot,
    render_dashboard_html,
    snapshot_json,
)


STATUS={
    "kind":"ALL_MARKET_FORWARD_READINESS_STATUS_NO_ORDERS",
    "checked_at_utc":"2026-10-01T04:10:28+00:00",
    "btc_and_six_crypto":{
        "sidecar_current_segment_independent_prospective_hours":18,
        "sidecar_fully_observed_precommitted_decision_intervals":17,
        "sidecar_review_gate_source_hours_remaining_to_169":151,
        "sidecar_review_gate_scored_outcomes_remaining_to_168":151,
        "sidecar_review_gate_evidence_window_complete":False,
        "sidecar_candidates_meeting_all_review_criteria":[],
    },
    "us_equity":{
        "session_plan_files":1,
        "prospective_core_hour_receipts":0,
        "raw_session_plans_remaining_to_10":9,
        "raw_core_hour_receipts_remaining_to_60":60,
        "decision_hours_capture_window_open":0,
        "prospective_source_integrity_ready_for_shadow_scoring":False,
    },
    "kalshi":{
        "plan_present":False,
        "planned_market_count":None,
        "prospective_decision_snapshots":0,
        "settlement_receipts":0,
        "raw_decision_snapshots_remaining":40,
        "raw_settlement_receipts_remaining":20,
        "prospective_source_integrity_ready_for_shadow_scoring":False,
    },
    "lane_next_actions":{
        "six_crypto":"CONTINUE_UNATTENDED_FORWARD_COLLECTION",
        "us_equity":"CONTINUE_UNATTENDED_STOCK_FORWARD_COLLECTION",
        "kalshi":"PRECOMMIT_PUBLIC_KALSHI_PROSPECTIVE_PLAN_GET_ONLY",
    },
    "automatic_cross_market_selection":"DISABLED",
    "network_requests":"NONE",
    "credential_access":"NONE",
    "broker_order_submission":"DISABLED",
    "paper_order_submission":"DISABLED",
    "demo_order_submission":"DISABLED",
    "live_order_submission":"DISABLED",
    "automatic_live_trading":"DISABLED",
    "live_trading":"UNAVAILABLE",
}


class AllMarketDashboardTests(unittest.TestCase):
    def test_snapshot_is_read_only_and_summarizes_all_lanes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            with patch(
                "signal_vault.all_market_dashboard.all_market_forward_status",
                return_value=STATUS,
            ):
                item=build_dashboard_snapshot(root=root,environ={})
        self.assertEqual(item["kind"],KIND)
        self.assertEqual(item["lanes"]["six_crypto"]["prospective_source_hours"],18)
        self.assertEqual(item["lanes"]["us_equity"]["session_plans"],1)
        self.assertFalse(item["lanes"]["kalshi"]["plan_present"])
        self.assertEqual(item["network_requests"],"NONE")
        self.assertEqual(item["credential_access"],"NONE")
        self.assertEqual(item["paper_order_submission"],"DISABLED")
        self.assertEqual(item["live_trading"],"UNAVAILABLE")
        self.assertTrue(item["paper_runway_blockers"])

    def test_html_contains_all_market_sections_without_execution_controls(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            with patch(
                "signal_vault.all_market_dashboard.all_market_forward_status",
                return_value=STATUS,
            ):
                item=build_dashboard_snapshot(root=root,environ={})
        html=render_dashboard_html(item).decode()
        self.assertIn("Six Crypto",html)
        self.assertIn("US Equities",html)
        self.assertIn("Kalshi",html)
        self.assertIn("PAPER: DISABLED",html)
        self.assertIn("LIVE: UNAVAILABLE",html)
        self.assertNotIn("<form",html.lower())
        self.assertNotIn("<button",html.lower())

    def test_json_export_preserves_no_order_contract(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            with patch(
                "signal_vault.all_market_dashboard.all_market_forward_status",
                return_value=STATUS,
            ):
                item=build_dashboard_snapshot(root=root,environ={})
        raw=snapshot_json(item).decode()
        self.assertIn('"paper_order_submission":"DISABLED"',raw)
        self.assertIn('"live_order_submission":"DISABLED"',raw)


if __name__=="__main__":
    unittest.main()

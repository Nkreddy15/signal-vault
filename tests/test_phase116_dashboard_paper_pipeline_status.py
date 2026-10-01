import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from signal_vault.all_market_dashboard import (
    build_dashboard_snapshot,
    render_dashboard_html,
)


STATUS={
    "kind":"ALL_MARKET_FORWARD_READINESS_STATUS_NO_ORDERS",
    "checked_at_utc":"2026-10-01T05:00:00+00:00",
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


class DashboardPaperPipelineStatusTests(unittest.TestCase):
    def test_snapshot_labels_engineering_capabilities_without_enabling_orders(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            with patch(
                "signal_vault.all_market_dashboard.all_market_forward_status",
                return_value=STATUS,
            ):
                item=build_dashboard_snapshot(root=root,environ={})
        eng=item["execution_engineering"]
        self.assertEqual(
            eng["shared_cross_market_risk_governor"],
            "AVAILABLE",
        )
        self.assertEqual(
            eng["crypto_end_to_end_paper_dry_run"],
            "AVAILABLE_NO_EXECUTION",
        )
        self.assertEqual(
            eng["autonomous_paper_activation"],
            "DISABLED_PENDING_FORWARD_EVIDENCE_AND_OWNER_REVIEW",
        )
        self.assertEqual(eng["live_execution"],"UNAVAILABLE")
        self.assertEqual(item["paper_order_submission"],"DISABLED")
        self.assertEqual(item["live_order_submission"],"DISABLED")

    def test_older_persisted_snapshot_renders_with_fail_safe_pipeline_defaults(self):
        old={
            "kind":"SIGNAL_VAULT_ALL_MARKET_OPERATOR_DASHBOARD_READ_ONLY",
            "checked_at_utc":"2026-10-01T04:10:28+00:00",
            "lanes":{
                "six_crypto":{
                    "prospective_source_hours":18,
                    "fully_scored_outcomes":17,
                    "source_hours_remaining":151,
                    "scored_outcomes_remaining":151,
                    "next_action":"CONTINUE_UNATTENDED_FORWARD_COLLECTION",
                },
                "us_equity":{
                    "session_plans":1,
                    "core_hour_receipts":0,
                    "session_plans_remaining":9,
                    "core_hour_receipts_remaining":60,
                    "capture_windows_open":0,
                    "next_action":"CONTINUE_UNATTENDED_STOCK_FORWARD_COLLECTION",
                },
                "kalshi":{
                    "plan_present":False,
                    "planned_markets":None,
                    "decision_snapshots":0,
                    "settlements":0,
                    "decision_snapshots_remaining":40,
                    "settlements_remaining":20,
                    "next_action":"PRECOMMIT_PUBLIC_KALSHI_PROSPECTIVE_PLAN_GET_ONLY",
                },
            },
            "paper_runway_blockers":[
                "SIX_CRYPTO_FROZEN_FORWARD_REVIEW_WINDOW_INCOMPLETE"
            ],
            "all_forward_stages_complete":False,
            "paper_order_submission":"DISABLED",
            "demo_order_submission":"DISABLED",
            "live_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
            "network_requests":"NONE",
            "credential_access":"NONE",
        }
        html=render_dashboard_html(old).decode()
        self.assertIn("PAPER Pipeline",html)
        self.assertIn("NOT_RECORDED_IN_THIS_SNAPSHOT",html)
        self.assertIn("Autonomous activation</span><strong>DISABLED",html)
        self.assertIn("LIVE</span><strong>UNAVAILABLE",html)
        self.assertNotIn("<button",html.lower())
        self.assertNotIn("<form",html.lower())

    def test_html_shows_pipeline_as_status_not_execution_controls(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            with patch(
                "signal_vault.all_market_dashboard.all_market_forward_status",
                return_value=STATUS,
            ):
                item=build_dashboard_snapshot(root=root,environ={})
        html=render_dashboard_html(item).decode()
        self.assertIn("PAPER Pipeline",html)
        self.assertIn("AVAILABLE_NO_EXECUTION",html)
        self.assertIn(
            "DISABLED_PENDING_FORWARD_EVIDENCE_AND_OWNER_REVIEW",
            html,
        )
        self.assertNotIn("<button",html.lower())
        self.assertNotIn("<form",html.lower())


if __name__=="__main__":
    unittest.main()

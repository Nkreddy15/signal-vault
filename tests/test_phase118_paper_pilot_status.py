import unittest

from signal_vault.paper_pilot_status import (
    KIND,
    paper_pilot_status_from_forward,
)


def forward_status():
    return {
        "kind":"ALL_MARKET_FORWARD_READINESS_STATUS_NO_ORDERS",
        "btc_and_six_crypto":{
            "sidecar_current_segment_independent_prospective_hours":18,
            "sidecar_fully_observed_precommitted_decision_intervals":17,
            "sidecar_review_gate_source_hours_remaining_to_169":151,
            "sidecar_review_gate_scored_outcomes_remaining_to_168":151,
            "sidecar_review_gate_evidence_window_complete":False,
            "sidecar_candidates_meeting_all_review_criteria":[],
        },
        "us_equity":{
            "raw_core_hour_receipts_remaining_to_60":60,
            "raw_session_plans_remaining_to_10":9,
            "prospective_source_integrity_ready_for_shadow_scoring":False,
        },
        "kalshi":{
            "plan_present":False,
            "planned_market_count":None,
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


class PaperPilotStatusTests(unittest.TestCase):
    def test_status_separates_built_engineering_from_missing_forward_evidence(self):
        result=paper_pilot_status_from_forward(forward_status())
        self.assertEqual(result["kind"],KIND)
        self.assertEqual(
            result["engineering"]["crypto_end_to_end_paper_dry_run"],
            "AVAILABLE_NO_EXECUTION",
        )
        self.assertFalse(
            result["crypto_autonomous_paper"]["forward_evidence_complete"]
        )
        self.assertFalse(
            result["crypto_autonomous_paper"][
                "candidate_available_after_frozen_review"
            ]
        )
        self.assertFalse(
            result["all_market_autonomous_paper"][
                "ready_for_unattended_order_submission"
            ]
        )
        self.assertGreater(
            result["all_market_autonomous_paper"][
                "forward_evidence_blocker_count"
            ],
            0,
        )
        self.assertEqual(result["network_requests"],"NONE")
        self.assertEqual(result["credential_access"],"NONE")
        self.assertEqual(result["paper_order_submission"],"DISABLED")
        self.assertEqual(result["live_trading"],"UNAVAILABLE")

    def test_complete_forward_window_still_does_not_enable_executor(self):
        status=forward_status()
        status["btc_and_six_crypto"]={
            **status["btc_and_six_crypto"],
            "sidecar_current_segment_independent_prospective_hours":169,
            "sidecar_fully_observed_precommitted_decision_intervals":168,
            "sidecar_review_gate_source_hours_remaining_to_169":0,
            "sidecar_review_gate_scored_outcomes_remaining_to_168":0,
            "sidecar_review_gate_evidence_window_complete":True,
            "sidecar_candidates_meeting_all_review_criteria":[
                "generic-ema12x26-v1-predeclared"
            ],
        }
        result=paper_pilot_status_from_forward(status)
        self.assertTrue(
            result["crypto_autonomous_paper"]["forward_evidence_complete"]
        )
        self.assertTrue(
            result["crypto_autonomous_paper"][
                "candidate_available_after_frozen_review"
            ]
        )
        self.assertFalse(
            result["crypto_autonomous_paper"]["executor_invocation_enabled"]
        )
        self.assertTrue(
            result["crypto_autonomous_paper"]["owner_activation_review_required"]
        )
        self.assertEqual(result["paper_order_submission"],"DISABLED")


if __name__=="__main__":
    unittest.main()

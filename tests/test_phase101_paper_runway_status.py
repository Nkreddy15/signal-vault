import unittest

from signal_vault.paper_runway_status import paper_runway_from_forward_status


def status(
    *,
    crypto_hours=13,
    crypto_scored=12,
    crypto_complete=False,
    crypto_eligible=None,
    equity_hours_remaining=60,
    equity_sessions_remaining=10,
    equity_ready=False,
    kalshi_plan=False,
    kalshi_planned=None,
    kalshi_snapshots_remaining=40,
    kalshi_settlements_remaining=20,
    kalshi_ready=False,
):
    return {
        "kind":"ALL_MARKET_FORWARD_READINESS_STATUS_NO_ORDERS",
        "btc_and_six_crypto":{
            "sidecar_current_segment_independent_prospective_hours":crypto_hours,
            "sidecar_fully_observed_precommitted_decision_intervals":crypto_scored,
            "sidecar_review_gate_source_hours_remaining_to_169":max(0,169-crypto_hours),
            "sidecar_review_gate_scored_outcomes_remaining_to_168":max(0,168-crypto_scored),
            "sidecar_review_gate_evidence_window_complete":crypto_complete,
            "sidecar_candidates_meeting_all_review_criteria":crypto_eligible or [],
        },
        "us_equity":{
            "raw_core_hour_receipts_remaining_to_60":equity_hours_remaining,
            "raw_session_plans_remaining_to_10":equity_sessions_remaining,
            "prospective_source_integrity_ready_for_shadow_scoring":equity_ready,
        },
        "kalshi":{
            "plan_present":kalshi_plan,
            "planned_market_count":kalshi_planned,
            "raw_decision_snapshots_remaining":kalshi_snapshots_remaining,
            "raw_settlement_receipts_remaining":kalshi_settlements_remaining,
            "prospective_source_integrity_ready_for_shadow_scoring":kalshi_ready,
        },
        "lane_next_actions":{
            "six_crypto":"CONTINUE_UNATTENDED_FORWARD_COLLECTION",
            "us_equity":"WAIT_FOR_NEXT_XNYS_PREMARKET_SESSION_PLAN",
            "kalshi":"PRECOMMIT_PUBLIC_KALSHI_PROSPECTIVE_PLAN_GET_ONLY",
        },
        "broker_order_submission":"DISABLED",
        "paper_order_submission":"DISABLED",
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "automatic_live_trading":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


class PaperRunwayStatusTests(unittest.TestCase):
    def test_current_incomplete_lanes_remain_blocked_without_order_authority(self):
        result=paper_runway_from_forward_status(status())
        self.assertEqual(
            result["six_crypto"]["source_hours_remaining_to_frozen_169_hour_gate"],
            156,
        )
        self.assertEqual(
            result["six_crypto"]["scored_outcomes_remaining_to_frozen_168_outcome_gate"],
            156,
        )
        self.assertEqual(
            result["us_equity"]["core_hour_receipts_remaining_to_60"],60
        )
        self.assertEqual(result["kalshi"]["decision_snapshots_remaining"],40)
        self.assertEqual(len(result["current_forward_evidence_blockers"]),3)
        self.assertFalse(result["all_market_forward_source_and_review_stages_complete"])
        self.assertTrue(
            result["owner_authorization_required_for_any_new_paper_or_demo_submission"]
        )
        self.assertEqual(result["paper_order_submission"],"DISABLED")
        self.assertEqual(result["demo_order_submission"],"DISABLED")
        self.assertEqual(result["live_trading"],"UNAVAILABLE")

    def test_complete_forward_sources_still_do_not_authorize_execution(self):
        result=paper_runway_from_forward_status(status(
            crypto_hours=169,
            crypto_scored=168,
            crypto_complete=True,
            crypto_eligible=["generic-ema12x26-v1-predeclared"],
            equity_hours_remaining=0,
            equity_sessions_remaining=0,
            equity_ready=True,
            kalshi_plan=True,
            kalshi_planned=22,
            kalshi_snapshots_remaining=0,
            kalshi_settlements_remaining=0,
            kalshi_ready=True,
        ))
        self.assertEqual(result["current_forward_evidence_blockers"],[])
        self.assertTrue(result["all_market_forward_source_and_review_stages_complete"])
        self.assertEqual(
            result["execution_engineering_and_prior_supervised_paper_smoke"],
            "NOT_TRACKED_BY_THIS_CLOUD_FORWARD_STATUS",
        )
        self.assertEqual(
            result["provider_paper_or_demo_execution_validation"],
            "NOT_TRACKED_BY_THIS_CLOUD_FORWARD_STATUS",
        )
        self.assertEqual(result["automatic_paper_or_demo_submission"],"DISABLED")
        self.assertTrue(
            result["owner_authorization_required_for_any_new_paper_or_demo_submission"]
        )

    def test_complete_crypto_window_without_eligible_candidate_remains_blocked(self):
        result=paper_runway_from_forward_status(status(
            crypto_hours=169,
            crypto_scored=168,
            crypto_complete=True,
            crypto_eligible=[],
        ))
        self.assertIn(
            "SIX_CRYPTO_FORWARD_WINDOW_COMPLETE_NO_CANDIDATE_ELIGIBLE",
            result["current_forward_evidence_blockers"],
        )

    def test_unsafe_input_is_rejected(self):
        raw=status()
        raw["paper_order_submission"]="ENABLED"
        with self.assertRaises(ValueError):
            paper_runway_from_forward_status(raw)


if __name__=="__main__":
    unittest.main()

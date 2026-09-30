import unittest

from signal_vault.kalshi_research_readiness import (
    kalshi_research_readiness_receipt,
)


def depth(ready=True):
    return {
        "kind":"KALSHI_HISTORICAL_DEPTH_GATE_PREDECLARED_NO_ORDER",
        "historical_depth_ready_for_fixed_strategy_research":ready,
        "demo_execution_eligible":False,
        "live_execution_eligible":False,
        "order_submission":"DISABLED",
    }


def walk(ready=True):
    return {
        "kind":"OFFLINE_KALSHI_EXPANDING_WALK_FORWARD_RESEARCH",
        "resolved_market_count":50,
        "historical_walk_forward_complete":ready,
        "historical_walk_forward_is_not_prospective_validation":True,
        "strategy_selection_performed":False,
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
    }


def confirmation(candidates=None):
    candidates=["market-favorite-6h-hold-v1-predeclared"] if candidates is None else candidates
    return {
        "kind":"KALSHI_UNTOUCHED_TEST_CONFIRMATION_NO_ORDER",
        "candidates_confirmed_on_untouched_test":candidates,
        "candidate_added_by_untouched_test":False,
        "candidate_ranking_performed":False,
        "automatic_candidate_selection":"DISABLED",
        "eligible_for_demo_execution_design_review":bool(candidates),
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
    }


class KalshiResearchReadinessReceiptTests(unittest.TestCase):
    def test_historical_success_only_opens_demo_design_review_not_execution(self):
        result=kalshi_research_readiness_receipt(
            depth(),walk(),confirmation()
        )
        self.assertTrue(result["historical_depth_ready"])
        self.assertTrue(result["historical_walk_forward_complete"])
        self.assertTrue(result["historical_candidate_confirmed"])
        self.assertTrue(
            result["ready_for_separate_demo_execution_design_review"]
        )
        lane=result["shared_lane_readiness"]
        self.assertTrue(lane["evidence"]["historical_dataset_verified"])
        self.assertTrue(lane["evidence"]["historical_walk_forward_complete"])
        self.assertTrue(lane["evidence"]["frozen_model_or_ruleset"])
        self.assertFalse(lane["evidence"]["prospective_or_shadow_complete"])
        self.assertFalse(lane["evidence"]["paper_or_demo_execution_validated"])
        self.assertFalse(
            lane["evidence"][
                "restart_and_unknown_result_recovery_validated"
            ]
        )
        self.assertFalse(
            lane["evidence"]["provider_reconciliation_validated"]
        )
        self.assertFalse(
            lane["technically_ready_for_live_activation_review"]
        )
        self.assertFalse(lane["live_activation_permitted"])
        self.assertEqual(result["demo_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")

    def test_missing_depth_walk_forward_or_candidate_keeps_demo_design_closed(self):
        cases=(
            (depth(False),walk(),confirmation()),
            (depth(),walk(False),confirmation()),
            (depth(),walk(),confirmation([])),
        )
        for args in cases:
            with self.subTest(args=args):
                result=kalshi_research_readiness_receipt(*args)
                self.assertFalse(
                    result["ready_for_separate_demo_execution_design_review"]
                )
                self.assertFalse(
                    result["shared_lane_readiness"][
                        "live_activation_permitted"
                    ]
                )

    def test_bad_historical_receipts_fail_closed(self):
        bad=depth()
        bad["order_submission"]="ENABLED"
        with self.assertRaises(ValueError):
            kalshi_research_readiness_receipt(
                bad,walk(),confirmation()
            )

        bad=confirmation()
        bad["candidate_ranking_performed"]=True
        with self.assertRaises(ValueError):
            kalshi_research_readiness_receipt(
                depth(),walk(),bad
            )


if __name__=="__main__":
    unittest.main()

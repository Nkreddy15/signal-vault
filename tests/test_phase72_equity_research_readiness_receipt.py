import unittest

from signal_vault.equity_research_readiness import (
    equity_research_readiness_receipt,
)


CANDIDATE="generic-ema12x26-v1-predeclared"


def gate(candidates=None):
    candidates=[CANDIDATE] if candidates is None else candidates
    return {
        "kind":"EQUITY_PREDECLARED_HISTORICAL_CANDIDATE_GATE_NO_ORDER",
        "candidates_meeting_all_criteria":candidates,
        "candidate_ranking_performed":False,
        "automatic_candidate_selection":"DISABLED",
        "untouched_test_accessed_for_candidate_selection":False,
        "broker_order_submission":"DISABLED",
    }


def confirmation(candidates=None):
    candidates=[CANDIDATE] if candidates is None else candidates
    return {
        "kind":"EQUITY_UNTOUCHED_TEST_CONFIRMATION_NO_ORDER",
        "candidates_confirmed_on_untouched_test":candidates,
        "candidate_added_by_untouched_test":False,
        "candidate_ranking_performed":False,
        "automatic_candidate_selection":"DISABLED",
        "paper_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
    }


def walk():
    return {
        "kind":"OFFLINE_EXPANDING_WALK_FORWARD_SIX_STOCK_RESEARCH",
        "historical_walk_forward_complete":True,
        "historical_walk_forward_is_not_prospective_validation":True,
        "strategy_selection_performed":False,
        "hyperparameter_optimization_performed":False,
        "broker_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


class EquityResearchReadinessReceiptTests(unittest.TestCase):
    def test_historical_success_still_leaves_shadow_paper_and_live_closed(self):
        result=equity_research_readiness_receipt(
            gate(),confirmation(),walk()
        )
        self.assertTrue(result["historical_dataset_verified"])
        self.assertTrue(result["historical_walk_forward_complete"])
        self.assertTrue(result["historical_candidate_confirmed"])
        self.assertTrue(result["ready_for_prospective_shadow_collection"])
        lane=result["shared_lane_readiness"]
        self.assertTrue(lane["evidence"]["historical_dataset_verified"])
        self.assertTrue(lane["evidence"]["historical_walk_forward_complete"])
        self.assertTrue(lane["evidence"]["frozen_model_or_ruleset"])
        self.assertFalse(lane["evidence"]["prospective_or_shadow_complete"])
        self.assertFalse(lane["evidence"]["paper_or_demo_execution_validated"])
        self.assertFalse(lane["evidence"]["provider_reconciliation_validated"])
        self.assertFalse(lane["live_activation_permitted"])
        self.assertEqual(result["paper_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")

    def test_no_untouched_survivor_keeps_frozen_candidate_false(self):
        result=equity_research_readiness_receipt(
            gate(),confirmation([]),walk()
        )
        self.assertFalse(result["historical_candidate_confirmed"])
        self.assertFalse(result["ready_for_prospective_shadow_collection"])
        self.assertFalse(
            result["shared_lane_readiness"]["evidence"][
                "frozen_model_or_ruleset"
            ]
        )

    def test_untouched_candidate_not_in_historical_gate_is_rejected(self):
        with self.assertRaises(ValueError):
            equity_research_readiness_receipt(
                gate([]),confirmation([CANDIDATE]),walk()
            )

    def test_bad_walk_forward_contract_fails_closed(self):
        bad=walk()
        bad["strategy_selection_performed"]=True
        with self.assertRaises(ValueError):
            equity_research_readiness_receipt(
                gate(),confirmation(),bad
            )


if __name__=="__main__":
    unittest.main()

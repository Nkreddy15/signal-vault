import unittest

from signal_vault.kalshi_historical_candidate_gate import (
    CANDIDATES,
    REQUIRED_SCENARIOS,
)
from signal_vault.kalshi_untouched_confirmation_gate import (
    POLICY_VERSION,
    confirm_kalshi_untouched_candidates,
)


def historical_gate(candidates=None):
    candidates=list(CANDIDATES if candidates is None else candidates)
    return {
        "kind":"KALSHI_PREDECLARED_HISTORICAL_CANDIDATE_GATE_NO_ORDER",
        "candidates_meeting_all_criteria":candidates,
        "candidate_ranking_performed":False,
        "automatic_candidate_selection":"DISABLED",
        "untouched_test_accessed_for_candidate_selection":False,
        "demo_execution_eligible":False,
        "live_execution_eligible":False,
        "order_submission":"DISABLED",
    }


def fold(pnl="0.25", contracts=5, blocked=0):
    return {
        "market_count":10,
        "hypothetical_contract_count":contracts,
        "entry_blocked_market_count":blocked,
        "total_hypothetical_pnl_dollars":pnl,
        "mean_hypothetical_pnl_per_market_dollars":"0.025",
        "positive_pnl_market_count":5,
        "negative_pnl_market_count":0,
        "zero_pnl_market_count":5,
    }


def chronological():
    scenarios={}
    for scenario in REQUIRED_SCENARIOS:
        hypotheses={}
        for candidate in CANDIDATES:
            hypotheses[candidate]={
                "development":fold(),
                "validation":fold(),
                "untouched_test":fold(),
            }
        scenarios[scenario]={
            "extra_entry_friction_dollars":"0.01",
            "hypotheses":hypotheses,
        }
    return {
        "kind":"OFFLINE_KALSHI_CHRONOLOGICAL_THREE_WAY_RESEARCH",
        "resolved_market_count":50,
        "friction_scenarios":scenarios,
        "untouched_test_used_for_strategy_selection":False,
        "strategy_ranking_performed":False,
        "strategy_selection_performed":False,
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
    }


class KalshiUntouchedConfirmationGateTests(unittest.TestCase):
    def test_only_upstream_candidates_can_be_confirmed_and_no_demo_order_is_enabled(self):
        upstream=CANDIDATES[:2]
        result=confirm_kalshi_untouched_candidates(
            historical_gate(upstream),chronological()
        )
        self.assertEqual(result["policy_version"],POLICY_VERSION)
        self.assertEqual(result["upstream_candidates"],list(upstream))
        self.assertEqual(
            set(result["candidates_confirmed_on_untouched_test"]),
            set(upstream),
        )
        self.assertFalse(result["candidate_added_by_untouched_test"])
        self.assertFalse(result["candidate_ranking_performed"])
        self.assertEqual(result["automatic_candidate_selection"],"DISABLED")
        self.assertTrue(result["eligible_for_demo_execution_design_review"])
        self.assertEqual(
            result["next_action"],
            "OWNER_DEMO_EXECUTION_DESIGN_REVIEW_REQUIRED",
        )
        self.assertEqual(result["demo_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")
        self.assertTrue(
            result[
                "separate_owner_authorization_required_for_any_demo_execution"
            ]
        )

    def test_negative_high_friction_untouched_result_rejects_without_rescuing(self):
        chrono=chronological()
        candidate=CANDIDATES[0]
        high=REQUIRED_SCENARIOS[1]
        chrono["friction_scenarios"][high]["hypotheses"][candidate][
            "untouched_test"
        ]["total_hypothetical_pnl_dollars"]="-0.01"
        result=confirm_kalshi_untouched_candidates(
            historical_gate([candidate]),chrono
        )
        self.assertEqual(result["candidates_confirmed_on_untouched_test"],[])
        self.assertEqual(
            result["candidates_rejected_on_untouched_test"],[candidate]
        )
        self.assertFalse(result["eligible_for_demo_execution_design_review"])
        self.assertEqual(
            result["next_action"],
            "NO_KALSHI_REFERENCE_SURVIVES_FROZEN_HISTORICAL_CONFIRMATION",
        )

    def test_low_activity_or_excess_blocking_rejects(self):
        candidate=CANDIDATES[0]

        chrono=chronological()
        chrono["friction_scenarios"][REQUIRED_SCENARIOS[0]][
            "hypotheses"
        ][candidate]["untouched_test"]["hypothetical_contract_count"]=2
        result=confirm_kalshi_untouched_candidates(
            historical_gate([candidate]),chrono
        )
        self.assertFalse(result["eligible_for_demo_execution_design_review"])

        chrono=chronological()
        chrono["friction_scenarios"][REQUIRED_SCENARIOS[0]][
            "hypotheses"
        ][candidate]["untouched_test"]["entry_blocked_market_count"]=3
        result=confirm_kalshi_untouched_candidates(
            historical_gate([candidate]),chrono
        )
        self.assertFalse(result["eligible_for_demo_execution_design_review"])

    def test_bad_upstream_or_bad_chronology_fails_closed(self):
        bad=historical_gate()
        bad["untouched_test_accessed_for_candidate_selection"]=True
        with self.assertRaises(ValueError):
            confirm_kalshi_untouched_candidates(bad,chronological())

        bad=chronological()
        bad["strategy_selection_performed"]=True
        with self.assertRaises(ValueError):
            confirm_kalshi_untouched_candidates(historical_gate(),bad)


if __name__=="__main__":
    unittest.main()

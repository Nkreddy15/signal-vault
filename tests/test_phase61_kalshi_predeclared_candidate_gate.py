import unittest

from signal_vault.kalshi_historical_candidate_gate import (
    CANDIDATES,
    POLICY_VERSION,
    REQUIRED_SCENARIOS,
    assess_kalshi_historical_candidates,
)


def fold(markets,contracts,pnl,blocked=0):
    return {
        "market_count":markets,
        "hypothetical_contract_count":contracts,
        "entry_blocked_market_count":blocked,
        "total_hypothetical_pnl_dollars":pnl,
        "mean_hypothetical_pnl_per_market_dollars":"0.01",
        "positive_pnl_market_count":contracts,
        "negative_pnl_market_count":0,
        "zero_pnl_market_count":markets-contracts,
    }


def chronological():
    scenarios={}
    for scenario in REQUIRED_SCENARIOS:
        hypotheses={}
        for candidate in CANDIDATES:
            hypotheses[candidate]={
                "development":fold(30,12,"1.20"),
                "validation":fold(10,5,"0.40"),
                # Deliberately negative. Candidate selection must never inspect it.
                "untouched_test":fold(10,5,"-9.99"),
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


def walk_forward():
    scenarios={}
    for scenario in REQUIRED_SCENARIOS:
        hypotheses={}
        for candidate in CANDIDATES:
            hypotheses[candidate]={
                "fold_count":3,
                "folds":[
                    {
                        "fold":1,
                        "prior_context_market_count":20,
                        "validation_market_count":10,
                        **fold(10,4,"0.20"),
                    },
                    {
                        "fold":2,
                        "prior_context_market_count":30,
                        "validation_market_count":10,
                        **fold(10,4,"-0.05"),
                    },
                    {
                        "fold":3,
                        "prior_context_market_count":40,
                        "validation_market_count":10,
                        **fold(10,4,"0.30"),
                    },
                ],
                "strategy_selected_from_fold_results":False,
                "thresholds_changed_from_fold_results":False,
            }
        scenarios[scenario]={
            "extra_entry_friction_dollars":"0.01",
            "hypotheses":hypotheses,
        }
    return {
        "kind":"OFFLINE_KALSHI_EXPANDING_WALK_FORWARD_RESEARCH",
        "resolved_market_count":50,
        "fold_count":3,
        "friction_scenarios":scenarios,
        "fold_results_used_to_modify_strategy":False,
        "strategy_ranking_performed":False,
        "strategy_selection_performed":False,
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
    }


class KalshiHistoricalCandidateGateTests(unittest.TestCase):
    def test_all_candidates_can_pass_independently_without_ranking_or_untouched_test(self):
        result=assess_kalshi_historical_candidates(
            chronological(),walk_forward()
        )
        self.assertEqual(result["policy_version"],POLICY_VERSION)
        self.assertEqual(
            set(result["candidates_meeting_all_criteria"]),set(CANDIDATES)
        )
        self.assertFalse(result["candidate_ranking_performed"])
        self.assertEqual(result["automatic_candidate_selection"],"DISABLED")
        self.assertFalse(
            result["untouched_test_accessed_for_candidate_selection"]
        )
        self.assertEqual(
            result["next_action"],
            "RUN_UNTOUCHED_TEST_CONFIRMATION_BEFORE_ANY_DEMO_DESIGN",
        )
        self.assertFalse(result["demo_execution_eligible"])
        self.assertFalse(result["live_execution_eligible"])
        self.assertTrue(
            result[
                "separate_owner_authorization_required_for_any_demo_execution"
            ]
        )

    def test_one_candidate_failure_does_not_change_other_candidates(self):
        chrono=chronological()
        scenario=REQUIRED_SCENARIOS[0]
        failed=CANDIDATES[0]
        chrono["friction_scenarios"][scenario]["hypotheses"][failed][
            "validation"
        ]["total_hypothetical_pnl_dollars"]="-0.01"
        result=assess_kalshi_historical_candidates(chrono,walk_forward())
        self.assertNotIn(failed,result["candidates_meeting_all_criteria"])
        self.assertEqual(
            set(result["candidates_meeting_all_criteria"]),
            set(CANDIDATES[1:]),
        )

    def test_activity_blocked_and_walk_forward_rules_fail_closed(self):
        chrono=chronological()
        wf=walk_forward()
        candidate=CANDIDATES[0]
        scenario=REQUIRED_SCENARIOS[0]

        chrono["friction_scenarios"][scenario]["hypotheses"][candidate][
            "development"
        ]["hypothetical_contract_count"]=7
        result=assess_kalshi_historical_candidates(chrono,wf)
        self.assertNotIn(candidate,result["candidates_meeting_all_criteria"])

        chrono=chronological()
        chrono["friction_scenarios"][scenario]["hypotheses"][candidate][
            "validation"
        ]["entry_blocked_market_count"]=3
        result=assess_kalshi_historical_candidates(chrono,wf)
        self.assertNotIn(candidate,result["candidates_meeting_all_criteria"])

        chrono=chronological()
        wf=walk_forward()
        folds=wf["friction_scenarios"][scenario]["hypotheses"][candidate][
            "folds"
        ]
        folds[0]["total_hypothetical_pnl_dollars"]="-1"
        folds[1]["total_hypothetical_pnl_dollars"]="-1"
        folds[2]["total_hypothetical_pnl_dollars"]="0.1"
        result=assess_kalshi_historical_candidates(chrono,wf)
        self.assertNotIn(candidate,result["candidates_meeting_all_criteria"])

    def test_bad_research_contract_or_mutated_walk_forward_strategy_is_rejected(self):
        chrono=chronological()
        chrono["untouched_test_used_for_strategy_selection"]=True
        with self.assertRaises(ValueError):
            assess_kalshi_historical_candidates(chrono,walk_forward())

        wf=walk_forward()
        wf["friction_scenarios"][REQUIRED_SCENARIOS[0]]["hypotheses"][
            CANDIDATES[0]
        ]["thresholds_changed_from_fold_results"]=True
        with self.assertRaises(ValueError):
            assess_kalshi_historical_candidates(chronological(),wf)


if __name__=="__main__":
    unittest.main()

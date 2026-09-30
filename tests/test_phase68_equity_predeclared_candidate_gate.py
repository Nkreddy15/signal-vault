import unittest

from signal_vault.equity_historical_candidate_gate import (
    CANDIDATES,
    PASSIVE,
    POLICY_VERSION,
    REQUIRED_SCENARIOS,
    assess_equity_historical_candidates,
)


def fold(pnl="0.50",fills=8,drawdown="2.0",halt=False):
    return {
        "evaluation_start_utc":"2026-01-01T00:00:00+00:00",
        "evaluation_end_utc_exclusive":"2026-01-10T00:00:00+00:00",
        "evaluation_core_hours":40,
        "net_pnl_if_hypothetically_liquidated_usd":pnl,
        "sampled_event_max_drawdown_usd":drawdown,
        "synthetic_fill_count":fills,
        "persistent_peak_drawdown_entry_halt":halt,
        "historical_assets_sha256":{"AAPL":"a"},
    }


def three_way():
    scenarios={}
    for scenario in REQUIRED_SCENARIOS:
        hypotheses={}
        hypotheses[PASSIVE]={
            "development":fold(pnl="0.10",fills=6),
            "validation":fold(pnl="0.05",fills=2),
            "untouched_test":fold(pnl="99.00",fills=2),
        }
        for candidate in CANDIDATES:
            hypotheses[candidate]={
                "development":fold(pnl="0.80",fills=8),
                "validation":fold(pnl="0.30",fills=3),
                # Deliberately awful; selection must not inspect it.
                "untouched_test":fold(pnl="-99.00",fills=3),
            }
        scenarios[scenario]={
            "assumptions":{},
            "hypotheses":hypotheses,
        }
    return {
        "kind":"OFFLINE_SHARED_SIX_STOCK_CHRONOLOGICAL_THREE_WAY_RESEARCH",
        "three_fixed_friction_scenarios":scenarios,
        "untouched_test_used_for_strategy_selection":False,
        "strategy_ranking_performed":False,
        "strategy_selection_performed":False,
        "broker_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


def wf_fold(index,cand_pnl="0.20",passive_pnl="0.05",fills=4):
    common={
        "fold":index,
        "train_context_core_hours":90+(index-1)*30,
        "validation_core_hours":30,
        "validation_start_utc":f"2026-01-{index:02d}T00:00:00+00:00",
        "validation_end_utc_exclusive":f"2026-01-{index+1:02d}T00:00:00+00:00",
        "sampled_event_max_drawdown_usd":"2",
        "persistent_peak_drawdown_entry_halt":False,
        "historical_assets_sha256":{"AAPL":"a"},
    }
    candidate={**common,
        "net_pnl_if_hypothetically_liquidated_usd":cand_pnl,
        "synthetic_fill_count":fills,
    }
    passive={**common,
        "net_pnl_if_hypothetically_liquidated_usd":passive_pnl,
        "synthetic_fill_count":2,
    }
    return candidate,passive


def walk_forward():
    scenarios={}
    for scenario in REQUIRED_SCENARIOS:
        passive=[]
        candidate_folds={candidate:[] for candidate in CANDIDATES}
        for i in range(1,4):
            cand,base=wf_fold(i)
            passive.append(base)
            for candidate in CANDIDATES:
                candidate_folds[candidate].append(dict(cand))
        hypotheses={
            PASSIVE:{
                "folds":passive,
                "fold_count":3,
                "strategy_selected_from_fold_results":False,
                "hyperparameter_tuning_from_fold_results":False,
            }
        }
        for candidate in CANDIDATES:
            hypotheses[candidate]={
                "folds":candidate_folds[candidate],
                "fold_count":3,
                "strategy_selected_from_fold_results":False,
                "hyperparameter_tuning_from_fold_results":False,
            }
        scenarios[scenario]={
            "assumptions":{},
            "hypotheses":hypotheses,
        }
    return {
        "kind":"OFFLINE_EXPANDING_WALK_FORWARD_SIX_STOCK_RESEARCH",
        "three_fixed_friction_scenarios":scenarios,
        "historical_walk_forward_complete":True,
        "historical_walk_forward_is_not_prospective_validation":True,
        "strategy_selection_performed":False,
        "hyperparameter_optimization_performed":False,
        "broker_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


class EquityHistoricalCandidateGateTests(unittest.TestCase):
    def test_candidates_pass_independently_without_reading_bad_untouched_fold(self):
        result=assess_equity_historical_candidates(
            three_way(),walk_forward()
        )
        self.assertEqual(result["policy_version"],POLICY_VERSION)
        self.assertEqual(
            set(result["candidates_meeting_all_criteria"]),
            set(CANDIDATES),
        )
        self.assertFalse(result["candidate_ranking_performed"])
        self.assertEqual(result["automatic_candidate_selection"],"DISABLED")
        self.assertFalse(
            result["untouched_test_accessed_for_candidate_selection"]
        )
        self.assertEqual(
            result["next_action"],
            "RUN_STOCK_UNTOUCHED_TEST_CONFIRMATION",
        )
        self.assertFalse(result["paper_execution_eligible"])
        self.assertFalse(result["live_execution_eligible"])
        self.assertEqual(result["broker_order_submission"],"DISABLED")

    def test_candidate_must_beat_passive_in_development_and_validation(self):
        report=three_way()
        candidate=CANDIDATES[0]
        scenario=REQUIRED_SCENARIOS[0]
        report["three_fixed_friction_scenarios"][scenario]["hypotheses"][
            candidate
        ]["validation"]["net_pnl_if_hypothetically_liquidated_usd"]="0.04"
        result=assess_equity_historical_candidates(
            report,walk_forward()
        )
        self.assertNotIn(candidate,result["candidates_meeting_all_criteria"])
        self.assertIn(CANDIDATES[1],result["candidates_meeting_all_criteria"])

    def test_walk_forward_must_beat_passive_majority_and_total(self):
        wf=walk_forward()
        candidate=CANDIDATES[0]
        scenario=REQUIRED_SCENARIOS[0]
        folds=wf["three_fixed_friction_scenarios"][scenario][
            "hypotheses"
        ][candidate]["folds"]
        folds[0]["net_pnl_if_hypothetically_liquidated_usd"]="0.01"
        folds[1]["net_pnl_if_hypothetically_liquidated_usd"]="0.01"
        folds[2]["net_pnl_if_hypothetically_liquidated_usd"]="0.50"
        result=assess_equity_historical_candidates(
            three_way(),wf
        )
        self.assertNotIn(candidate,result["candidates_meeting_all_criteria"])

    def test_low_activity_drawdown_halt_or_bad_contract_fails(self):
        report=three_way()
        candidate=CANDIDATES[0]
        scenario=REQUIRED_SCENARIOS[0]
        report["three_fixed_friction_scenarios"][scenario]["hypotheses"][
            candidate
        ]["development"]["synthetic_fill_count"]=5
        self.assertNotIn(
            candidate,
            assess_equity_historical_candidates(
                report,walk_forward()
            )["candidates_meeting_all_criteria"],
        )

        report=three_way()
        report["three_fixed_friction_scenarios"][scenario]["hypotheses"][
            candidate
        ]["validation"]["persistent_peak_drawdown_entry_halt"]=True
        self.assertNotIn(
            candidate,
            assess_equity_historical_candidates(
                report,walk_forward()
            )["candidates_meeting_all_criteria"],
        )

        report=three_way()
        report["untouched_test_used_for_strategy_selection"]=True
        with self.assertRaises(ValueError):
            assess_equity_historical_candidates(report,walk_forward())


if __name__=="__main__":
    unittest.main()

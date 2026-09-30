import unittest

from signal_vault.equity_historical_candidate_gate import (
    CANDIDATES,
    PASSIVE,
    REQUIRED_SCENARIOS,
)
from signal_vault.equity_untouched_confirmation_gate import (
    POLICY_VERSION,
    confirm_equity_untouched_candidates,
)


def gate(candidates=None):
    candidates=list(CANDIDATES if candidates is None else candidates)
    return {
        "kind":"EQUITY_PREDECLARED_HISTORICAL_CANDIDATE_GATE_NO_ORDER",
        "candidates_meeting_all_criteria":candidates,
        "candidate_ranking_performed":False,
        "automatic_candidate_selection":"DISABLED",
        "untouched_test_accessed_for_candidate_selection":False,
        "paper_execution_eligible":False,
        "live_execution_eligible":False,
        "broker_order_submission":"DISABLED",
    }


def fold(pnl="0.40",fills=3,drawdown="2",halt=False):
    return {
        "evaluation_start_utc":"2026-01-01T00:00:00+00:00",
        "evaluation_end_utc_exclusive":"2026-01-10T00:00:00+00:00",
        "evaluation_core_hours":20,
        "net_pnl_if_hypothetically_liquidated_usd":pnl,
        "sampled_event_max_drawdown_usd":drawdown,
        "synthetic_fill_count":fills,
        "persistent_peak_drawdown_entry_halt":halt,
        "historical_assets_sha256":{"AAPL":"a"},
    }


def three_way():
    scenarios={}
    for scenario in REQUIRED_SCENARIOS:
        hypotheses={
            PASSIVE:{
                "development":fold(),
                "validation":fold(),
                "untouched_test":fold(pnl="0.10",fills=2),
            }
        }
        for candidate in CANDIDATES:
            hypotheses[candidate]={
                "development":fold(),
                "validation":fold(),
                "untouched_test":fold(pnl="0.50",fills=3),
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


class EquityUntouchedConfirmationGateTests(unittest.TestCase):
    def test_only_upstream_candidates_can_survive_and_no_paper_order_is_enabled(self):
        upstream=CANDIDATES[:1]
        result=confirm_equity_untouched_candidates(
            gate(upstream),three_way()
        )
        self.assertEqual(result["policy_version"],POLICY_VERSION)
        self.assertEqual(result["upstream_candidates"],list(upstream))
        self.assertEqual(
            result["candidates_confirmed_on_untouched_test"],list(upstream)
        )
        self.assertFalse(result["candidate_added_by_untouched_test"])
        self.assertFalse(result["candidate_ranking_performed"])
        self.assertEqual(result["automatic_candidate_selection"],"DISABLED")
        self.assertEqual(
            result["next_action"],
            "START_PROSPECTIVE_STOCK_SHADOW_COLLECTION",
        )
        self.assertFalse(result["eligible_for_paper_execution_design_review"])
        self.assertEqual(result["paper_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")

    def test_negative_or_passive_underperformance_rejects_without_rescue(self):
        candidate=CANDIDATES[0]
        report=three_way()
        high=REQUIRED_SCENARIOS[1]
        report["three_fixed_friction_scenarios"][high]["hypotheses"][
            candidate
        ]["untouched_test"]["net_pnl_if_hypothetically_liquidated_usd"]="0.05"
        result=confirm_equity_untouched_candidates(
            gate([candidate]),report
        )
        self.assertEqual(result["candidates_confirmed_on_untouched_test"],[])
        self.assertEqual(
            result["candidates_rejected_on_untouched_test"],[candidate]
        )

    def test_low_activity_drawdown_or_halt_rejects(self):
        candidate=CANDIDATES[0]
        scenario=REQUIRED_SCENARIOS[0]

        report=three_way()
        report["three_fixed_friction_scenarios"][scenario]["hypotheses"][
            candidate
        ]["untouched_test"]["synthetic_fill_count"]=1
        self.assertEqual(
            confirm_equity_untouched_candidates(
                gate([candidate]),report
            )["candidates_confirmed_on_untouched_test"],
            [],
        )

        report=three_way()
        report["three_fixed_friction_scenarios"][scenario]["hypotheses"][
            candidate
        ]["untouched_test"]["sampled_event_max_drawdown_usd"]="11"
        self.assertEqual(
            confirm_equity_untouched_candidates(
                gate([candidate]),report
            )["candidates_confirmed_on_untouched_test"],
            [],
        )

        report=three_way()
        report["three_fixed_friction_scenarios"][scenario]["hypotheses"][
            candidate
        ]["untouched_test"]["persistent_peak_drawdown_entry_halt"]=True
        self.assertEqual(
            confirm_equity_untouched_candidates(
                gate([candidate]),report
            )["candidates_confirmed_on_untouched_test"],
            [],
        )

    def test_bad_upstream_or_research_contract_fails_closed(self):
        bad=gate()
        bad["untouched_test_accessed_for_candidate_selection"]=True
        with self.assertRaises(ValueError):
            confirm_equity_untouched_candidates(bad,three_way())

        bad=three_way()
        bad["strategy_selection_performed"]=True
        with self.assertRaises(ValueError):
            confirm_equity_untouched_candidates(gate(),bad)


if __name__=="__main__":
    unittest.main()

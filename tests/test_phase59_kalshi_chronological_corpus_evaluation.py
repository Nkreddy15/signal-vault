import unittest
from datetime import datetime, timedelta, timezone

from signal_vault.kalshi_reference_hypotheses import HYPOTHESES
from signal_vault.offline_kalshi_chronological_research import (
    chronological_corpus_summary,
)
from signal_vault.offline_kalshi_strategy_simulation import FRICTION_SCENARIOS


def simulation(i):
    settled=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(days=i)
    scenarios={}
    for scenario in FRICTION_SCENARIOS:
        hypotheses={}
        for h_index,h in enumerate(HYPOTHESES):
            if h.mode=="cash":
                count=0
                pnl="0"
            else:
                count=1
                # Deterministic mix of positive/negative historical examples.
                pnl="0.10" if (i+h_index)%2==0 else "-0.05"
            hypotheses[h.name]={
                "decision":{"action":"hold" if count==0 else "buy_yes"},
                "entry_reference":"NONE" if count==0 else "YES_ASK_CLOSE",
                "extra_entry_friction_dollars":
                    str(FRICTION_SCENARIOS[scenario]),
                "hypothetical_contract_count":count,
                "hypothetical_pnl_dollars":pnl,
                "entry_blocked":False,
            }
        scenarios[scenario]={
            "extra_entry_friction_dollars":str(FRICTION_SCENARIOS[scenario]),
            "friction_is_illustrative_not_provider_fee_schedule":True,
            "hypotheses":hypotheses,
        }
    return {
        "kind":"OFFLINE_KALSHI_FROZEN_REFERENCE_STRATEGY_SIMULATION",
        "ticker":f"TEST-{i:03d}",
        "resolved_result":"yes" if i%2==0 else "no",
        "settlement_ts":settled.isoformat(),
        "source_manifest_sha256":f"{i:064x}",
        "fixed_hypotheses":[x.name for x in HYPOTHESES],
        "friction_scenarios":scenarios,
        "decision_made_before_outcome_scoring":True,
        "historical_quote_close_is_not_guaranteed_fill":True,
        "historical_orderbook_depth_reconstructed":False,
        "provider_fee_schedule_modeled":False,
        "strategy_selection_performed":False,
        "automatic_strategy_promotion":"DISABLED",
        "credentials_accessed":"NONE",
        "network_requests":"NONE",
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


class KalshiChronologicalCorpusResearchTests(unittest.TestCase):
    def test_exact_fifty_markets_get_fixed_30_10_10_split_without_selection(self):
        # Reverse input order to prove split is based on settlement chronology.
        result=chronological_corpus_summary(
            list(reversed([simulation(i) for i in range(50)]))
        )
        self.assertEqual(result["resolved_market_count"],50)
        self.assertEqual(
            result["chronological_split"]["development_markets"],30
        )
        self.assertEqual(
            result["chronological_split"]["validation_markets"],10
        )
        self.assertEqual(
            result["chronological_split"]["untouched_test_markets"],10
        )
        self.assertTrue(result["chronological_three_way_complete"])
        self.assertFalse(result["historical_walk_forward_complete"])
        self.assertFalse(result["untouched_test_used_for_strategy_selection"])
        self.assertFalse(result["strategy_ranking_performed"])
        self.assertFalse(result["strategy_selection_performed"])
        self.assertFalse(result["hyperparameter_optimization_performed"])
        self.assertEqual(result["demo_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")

        for scenario in result["friction_scenarios"].values():
            self.assertEqual(
                set(scenario["hypotheses"]),
                {x.name for x in HYPOTHESES},
            )
            for folds in scenario["hypotheses"].values():
                self.assertEqual(
                    set(folds),
                    {"development","validation","untouched_test"},
                )
                self.assertEqual(folds["development"]["market_count"],30)
                self.assertEqual(folds["validation"]["market_count"],10)
                self.assertEqual(folds["untouched_test"]["market_count"],10)

    def test_wrong_size_duplicate_or_unsafe_child_simulation_fails_closed(self):
        with self.assertRaises(ValueError):
            chronological_corpus_summary([simulation(i) for i in range(49)])

        duplicate=[simulation(i) for i in range(50)]
        duplicate[-1]["ticker"]=duplicate[0]["ticker"]
        with self.assertRaises(ValueError):
            chronological_corpus_summary(duplicate)

        unsafe=[simulation(i) for i in range(50)]
        unsafe[0]["strategy_selection_performed"]=True
        with self.assertRaises(ValueError):
            chronological_corpus_summary(unsafe)


if __name__=="__main__":
    unittest.main()

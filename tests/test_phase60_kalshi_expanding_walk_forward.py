import unittest
from datetime import datetime, timedelta, timezone

from signal_vault.kalshi_reference_hypotheses import HYPOTHESES
from signal_vault.offline_kalshi_strategy_simulation import FRICTION_SCENARIOS
from signal_vault.offline_kalshi_walk_forward import expanding_kalshi_walk_forward


def simulation(i):
    settled=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(days=i)
    scenarios={}
    for scenario,friction in FRICTION_SCENARIOS.items():
        hypotheses={}
        for j,h in enumerate(HYPOTHESES):
            count=0 if h.mode=="cash" else 1
            pnl="0" if count==0 else ("0.08" if (i+j)%3 else "-0.04")
            hypotheses[h.name]={
                "decision":{"action":"hold" if count==0 else "buy_yes"},
                "entry_reference":"NONE" if count==0 else "YES_ASK_CLOSE",
                "extra_entry_friction_dollars":str(friction),
                "hypothetical_contract_count":count,
                "hypothetical_pnl_dollars":pnl,
                "entry_blocked":False,
            }
        scenarios[scenario]={
            "extra_entry_friction_dollars":str(friction),
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


class KalshiExpandingWalkForwardTests(unittest.TestCase):
    def test_three_later_blocks_use_expanding_prior_context_without_tuning(self):
        result=expanding_kalshi_walk_forward(
            list(reversed([simulation(i) for i in range(50)]))
        )
        self.assertEqual(result["fold_count"],3)
        self.assertEqual(result["initial_context_market_count"],20)
        self.assertEqual(result["validation_market_count_per_fold"],10)
        self.assertTrue(result["historical_walk_forward_complete"])
        self.assertTrue(
            result["historical_walk_forward_is_not_prospective_validation"]
        )
        self.assertFalse(result["fold_results_used_to_modify_strategy"])
        self.assertFalse(result["strategy_ranking_performed"])
        self.assertFalse(result["strategy_selection_performed"])
        self.assertFalse(result["hyperparameter_optimization_performed"])
        self.assertEqual(result["demo_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")

        for scenario in result["friction_scenarios"].values():
            for hypothesis in scenario["hypotheses"].values():
                self.assertEqual(hypothesis["fold_count"],3)
                self.assertEqual(
                    [x["prior_context_market_count"]
                     for x in hypothesis["folds"]],
                    [20,30,40],
                )
                self.assertTrue(
                    all(x["validation_market_count"]==10
                        for x in hypothesis["folds"])
                )
                self.assertFalse(
                    hypothesis["strategy_selected_from_fold_results"]
                )
                self.assertFalse(
                    hypothesis["thresholds_changed_from_fold_results"]
                )

    def test_wrong_size_duplicate_and_unsafe_state_fail_closed(self):
        with self.assertRaises(ValueError):
            expanding_kalshi_walk_forward([simulation(i) for i in range(49)])

        dup=[simulation(i) for i in range(50)]
        dup[-1]["ticker"]=dup[0]["ticker"]
        with self.assertRaises(ValueError):
            expanding_kalshi_walk_forward(dup)

        unsafe=[simulation(i) for i in range(50)]
        unsafe[0]["strategy_selection_performed"]=True
        with self.assertRaises(ValueError):
            expanding_kalshi_walk_forward(unsafe)


if __name__=="__main__":
    unittest.main()

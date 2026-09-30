import unittest

from signal_vault.equity_historical_candidate_gate import (
    CANDIDATES,
    REQUIRED_SCENARIOS,
)
from signal_vault.equity_prospective_shadow_gate import (
    POLICY_VERSION,
    assess_equity_prospective_shadow,
)


CANDIDATE=CANDIDATES[0]


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


def scenario(pnl="0.40",passive="0.10",fills=4,drawdown="2",halt=False):
    return {
        "synthetic_fill_count":fills,
        "net_pnl_if_hypothetically_liquidated_usd":pnl,
        "sampled_event_max_drawdown_usd":drawdown,
        "persistent_peak_drawdown_entry_halt":halt,
        "chronological_blocks":[
            {
                "block":1,
                "core_hours":30,
                "net_pnl_if_hypothetically_liquidated_usd":"0.20",
            },
            {
                "block":2,
                "core_hours":30,
                "net_pnl_if_hypothetically_liquidated_usd":"0.20",
            },
        ],
    }


def passive_scenario():
    return {
        "synthetic_fill_count":2,
        "net_pnl_if_hypothetically_liquidated_usd":"0.10",
        "sampled_event_max_drawdown_usd":"1",
        "persistent_peak_drawdown_entry_halt":False,
        "chronological_blocks":[
            {
                "block":1,
                "core_hours":30,
                "net_pnl_if_hypothetically_liquidated_usd":"0.05",
            },
            {
                "block":2,
                "core_hours":30,
                "net_pnl_if_hypothetically_liquidated_usd":"0.05",
            },
        ],
    }


def summary():
    return {
        "kind":"EQUITY_PROSPECTIVE_SHADOW_SUMMARY_NO_ORDERS",
        "symbols":["AAPL","AMD","MSFT","NVDA","QQQ","SPY"],
        "prospective_core_hours_per_asset":60,
        "distinct_xnys_sessions":10,
        "complete_six_stock_grid_verified":True,
        "candidate_versions_changed_after_start":False,
        "historical_backfill_count":0,
        "hidden_gap_or_interpolation_count":0,
        "source_integrity_passed":True,
        "candidate_results":{
            CANDIDATE:{
                name:scenario()
                for name in REQUIRED_SCENARIOS
            }
        },
        "passive_benchmark_results":{
            name:passive_scenario()
            for name in REQUIRED_SCENARIOS
        },
        "network_methods":["GET"],
        "broker_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
    }


class EquityProspectiveShadowGateTests(unittest.TestCase):
    def test_sixty_future_core_hours_can_complete_shadow_without_orders(self):
        result=assess_equity_prospective_shadow(
            confirmation(),summary()
        )
        self.assertEqual(result["policy_version"],POLICY_VERSION)
        self.assertEqual(
            result["candidates_passing_prospective_shadow"],[CANDIDATE]
        )
        self.assertTrue(result["prospective_or_shadow_complete"])
        self.assertFalse(result["candidate_added_by_prospective_results"])
        self.assertFalse(result["candidate_ranking_performed"])
        self.assertFalse(
            result["historical_data_substituted_for_prospective_evidence"]
        )
        self.assertEqual(result["paper_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")

    def test_candidate_must_beat_passive_in_both_blocks_and_total(self):
        item=summary()
        scenario_name=REQUIRED_SCENARIOS[1]
        item["candidate_results"][CANDIDATE][scenario_name][
            "chronological_blocks"
        ][1]["net_pnl_if_hypothetically_liquidated_usd"]="0.01"
        result=assess_equity_prospective_shadow(
            confirmation(),item
        )
        self.assertEqual(
            result["candidates_passing_prospective_shadow"],[]
        )
        self.assertFalse(result["prospective_or_shadow_complete"])

    def test_insufficient_hours_sessions_activity_drawdown_or_halt_fails(self):
        cases=[]
        item=summary()
        item["prospective_core_hours_per_asset"]=59
        cases.append(item)
        item=summary()
        item["distinct_xnys_sessions"]=9
        cases.append(item)
        item=summary()
        item["candidate_results"][CANDIDATE][REQUIRED_SCENARIOS[0]][
            "synthetic_fill_count"
        ]=1
        cases.append(item)
        item=summary()
        item["candidate_results"][CANDIDATE][REQUIRED_SCENARIOS[0]][
            "sampled_event_max_drawdown_usd"
        ]="11"
        cases.append(item)
        item=summary()
        item["candidate_results"][CANDIDATE][REQUIRED_SCENARIOS[0]][
            "persistent_peak_drawdown_entry_halt"
        ]=True
        cases.append(item)

        for item in cases:
            with self.subTest(item=item):
                result=assess_equity_prospective_shadow(
                    confirmation(),item
                )
                self.assertFalse(result["prospective_or_shadow_complete"])

    def test_backfill_gap_or_unconfirmed_candidate_is_rejected(self):
        item=summary()
        item["historical_backfill_count"]=1
        with self.assertRaises(ValueError):
            assess_equity_prospective_shadow(confirmation(),item)

        item=summary()
        item["hidden_gap_or_interpolation_count"]=1
        with self.assertRaises(ValueError):
            assess_equity_prospective_shadow(confirmation(),item)

        item=summary()
        item["candidate_results"]["not-confirmed"]={
            name:scenario() for name in REQUIRED_SCENARIOS
        }
        with self.assertRaises(ValueError):
            assess_equity_prospective_shadow(confirmation(),item)


if __name__=="__main__":
    unittest.main()

import unittest

from signal_vault.kalshi_historical_candidate_gate import REQUIRED_SCENARIOS
from signal_vault.kalshi_prospective_shadow_gate import (
    POLICY_VERSION,
    assess_kalshi_prospective_shadow,
)


CANDIDATE="market-favorite-6h-hold-v1-predeclared"


def confirmation(candidates=None):
    candidates=[CANDIDATE] if candidates is None else candidates
    return {
        "kind":"KALSHI_UNTOUCHED_TEST_CONFIRMATION_NO_ORDER",
        "candidates_confirmed_on_untouched_test":candidates,
        "candidate_added_by_untouched_test":False,
        "candidate_ranking_performed":False,
        "automatic_candidate_selection":"DISABLED",
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
    }


def scenario(pnl="0.40",contracts=18,block_pnls=("0.20","0.20")):
    return {
        "hypothetical_contract_count":contracts,
        "total_hypothetical_pnl_dollars":pnl,
        "chronological_blocks":[
            {
                "block":1,
                "market_count":10,
                "total_hypothetical_pnl_dollars":block_pnls[0],
            },
            {
                "block":2,
                "market_count":10,
                "total_hypothetical_pnl_dollars":block_pnls[1],
            },
        ],
    }


def summary():
    return {
        "kind":"KALSHI_PROSPECTIVE_SHADOW_SUMMARY_NO_ORDERS",
        "hypothesis_policy_version":
            "kalshi-reference-hypotheses-v1-predeclared-20260930",
        "candidate_versions_changed_after_start":False,
        "outcome_direction_used_for_market_selection":False,
        "planned_market_count":22,
        "valid_prospective_market_count":20,
        "distinct_event_count":12,
        "missed_or_invalid_market_count":2,
        "capture_coverage_fraction":str(20/22),
        "historical_backfill_count":0,
        "post_settlement_decision_count":0,
        "source_integrity_passed":True,
        "candidate_results":{
            CANDIDATE:{
                scenario_name:scenario()
                for scenario_name in REQUIRED_SCENARIOS
            }
        },
        "network_methods":["GET"],
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
    }


class KalshiProspectiveShadowGateTests(unittest.TestCase):
    def test_twenty_future_markets_can_complete_shadow_without_enabling_orders(self):
        item=summary()
        # Use exact decimal fraction string rather than float representation.
        item["capture_coverage_fraction"]="0.9090909090909090909090909091"
        result=assess_kalshi_prospective_shadow(
            confirmation(),item
        )
        self.assertEqual(result["policy_version"],POLICY_VERSION)
        self.assertEqual(
            result["candidates_passing_prospective_shadow"],[CANDIDATE]
        )
        self.assertTrue(result["prospective_or_shadow_complete"])
        self.assertFalse(result["candidate_added_by_prospective_results"])
        self.assertFalse(result["candidate_ranking_performed"])
        self.assertEqual(result["automatic_candidate_selection"],"DISABLED")
        self.assertFalse(
            result["historical_data_substituted_for_prospective_evidence"]
        )
        self.assertEqual(result["demo_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")
        self.assertFalse(result["owner_live_authorization_recorded"])

    def test_candidate_must_be_positive_in_both_blocks_base_and_high(self):
        item=summary()
        item["capture_coverage_fraction"]="0.9090909090909090909090909091"
        high=REQUIRED_SCENARIOS[1]
        item["candidate_results"][CANDIDATE][high]=scenario(
            pnl="0.19",block_pnls=("0.20","-0.01")
        )
        result=assess_kalshi_prospective_shadow(
            confirmation(),item
        )
        self.assertEqual(
            result["candidates_passing_prospective_shadow"],[]
        )
        self.assertFalse(result["prospective_or_shadow_complete"])
        self.assertEqual(
            result["next_action"],
            "CONTINUE_PROSPECTIVE_SHADOW_COLLECTION",
        )

    def test_low_coverage_market_count_event_count_or_activity_fails(self):
        cases=[]
        item=summary()
        item["planned_market_count"]=21
        item["valid_prospective_market_count"]=19
        item["missed_or_invalid_market_count"]=2
        item["capture_coverage_fraction"]=str(19/21)
        cases.append(item)

        item=summary()
        item["distinct_event_count"]=9
        item["capture_coverage_fraction"]="0.9090909090909090909090909091"
        cases.append(item)

        item=summary()
        item["capture_coverage_fraction"]="0.80"
        item["planned_market_count"]=25
        item["valid_prospective_market_count"]=20
        item["missed_or_invalid_market_count"]=5
        cases.append(item)

        item=summary()
        item["capture_coverage_fraction"]="0.9090909090909090909090909091"
        item["candidate_results"][CANDIDATE][REQUIRED_SCENARIOS[0]][
            "hypothetical_contract_count"
        ]=9
        cases.append(item)

        for item in cases:
            with self.subTest(item=item):
                result=assess_kalshi_prospective_shadow(
                    confirmation(),item
                )
                self.assertFalse(result["prospective_or_shadow_complete"])

    def test_backfill_post_settlement_or_unconfirmed_candidate_is_rejected(self):
        item=summary()
        item["historical_backfill_count"]=1
        with self.assertRaises(ValueError):
            assess_kalshi_prospective_shadow(confirmation(),item)

        item=summary()
        item["post_settlement_decision_count"]=1
        with self.assertRaises(ValueError):
            assess_kalshi_prospective_shadow(confirmation(),item)

        item=summary()
        item["candidate_results"]["not-confirmed"]={
            scenario_name:scenario()
            for scenario_name in REQUIRED_SCENARIOS
        }
        with self.assertRaises(ValueError):
            assess_kalshi_prospective_shadow(confirmation(),item)


if __name__=="__main__":
    unittest.main()

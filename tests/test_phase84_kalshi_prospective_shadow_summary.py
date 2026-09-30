import unittest

from signal_vault.kalshi_prospective_shadow_gate import (
    assess_kalshi_prospective_shadow,
)
from signal_vault.kalshi_prospective_shadow_summary import (
    build_kalshi_prospective_shadow_summary,
)


CANDIDATE="market-favorite-6h-hold-v1-predeclared"


def confirmation(candidate=CANDIDATE):
    return {
        "kind":"KALSHI_UNTOUCHED_TEST_CONFIRMATION_NO_ORDER",
        "candidate_added_by_untouched_test":False,
        "candidate_ranking_performed":False,
        "automatic_candidate_selection":"DISABLED",
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "candidates_confirmed_on_untouched_test":[candidate],
    }


def audit(*,pending=0,valid=20,missed=0):
    rows=[]
    for i in range(valid):
        rows.append({
            "ticker":f"MKT-{i:02d}",
            "event_ticker":f"EVT-{i//2:02d}",
            "planned_close_time_utc":f"2026-10-{10+i//2:02d}T20:00:00+00:00",
            "status":"VALID_COMPLETE",
            "invalid_reasons":[],
            "snapshots":{
                86400:{
                    "decision_valid":True,
                    "yes_bid_dollars":"0.58",
                    "yes_ask_dollars":"0.62",
                    "last_price_dollars":"0.60",
                },
                21600:{
                    "decision_valid":True,
                    "yes_bid_dollars":"0.58",
                    "yes_ask_dollars":"0.62",
                    "last_price_dollars":"0.60",
                },
            },
            "settlement":{
                "resolved_result":"yes",
                "settlement_ts":"2026-11-01T00:00:00+00:00",
                "captured_at_utc":"2026-11-01T01:00:00+00:00",
            },
        })
    for i in range(missed):
        rows.append({
            "ticker":f"BAD-{i:02d}",
            "event_ticker":f"BAD-EVT-{i:02d}",
            "planned_close_time_utc":"2026-11-20T20:00:00+00:00",
            "status":"MISSED_OR_INVALID",
            "invalid_reasons":["MISSED"],
            "snapshots":{},
            "settlement":None,
        })
    return {
        "kind":"KALSHI_PROSPECTIVE_ARCHIVE_AUDIT_NO_ORDERS",
        "plan_sha256":"a"*64,
        "hypothesis_policy_version":
            "kalshi-reference-hypotheses-v1-predeclared-20260930",
        "planned_market_count":valid+missed+pending,
        "valid_prospective_market_count":valid,
        "missed_or_invalid_market_count":missed,
        "pending_market_count":pending,
        "distinct_valid_event_count":len({
            x["event_ticker"] for x in rows if x["status"]=="VALID_COMPLETE"
        }),
        "capture_coverage_fraction":str(valid/(valid+missed+pending)),
        "markets":rows,
        "outcome_direction_used_for_market_selection":False,
        "historical_backfill_count":0,
        "post_settlement_decision_count":0,
        "source_integrity_passed":True,
        "network_requests":"NONE",
        "credentials_accessed":"NONE",
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


class KalshiProspectiveShadowSummaryTests(unittest.TestCase):
    def test_twenty_valid_markets_score_frozen_candidate_in_two_blocks(self):
        result=build_kalshi_prospective_shadow_summary(
            confirmation(),audit()
        )
        self.assertEqual(
            result["kind"],
            "KALSHI_PROSPECTIVE_SHADOW_SUMMARY_NO_ORDERS",
        )
        self.assertEqual(result["evaluation_market_count"],20)
        self.assertEqual(set(result["candidate_results"]),{CANDIDATE})
        for scenario in (
            "illustrative_base_extra_entry_friction",
            "illustrative_high_extra_entry_friction",
        ):
            scored=result["candidate_results"][CANDIDATE][scenario]
            self.assertEqual(scored["hypothetical_contract_count"],20)
            self.assertGreater(
                float(scored["total_hypothetical_pnl_dollars"]),0
            )
            self.assertEqual(
                [x["market_count"] for x in scored["chronological_blocks"]],
                [10,10],
            )
            self.assertTrue(all(
                float(x["total_hypothetical_pnl_dollars"])>0
                for x in scored["chronological_blocks"]
            ))
        self.assertFalse(result["candidate_added_by_prospective_results"])
        self.assertFalse(result["candidate_ranking_performed"])
        self.assertEqual(result["automatic_candidate_selection"],"DISABLED")
        self.assertEqual(result["demo_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")

    def test_output_is_directly_accepted_by_frozen_phase65_gate(self):
        summary=build_kalshi_prospective_shadow_summary(
            confirmation(),audit()
        )
        gate=assess_kalshi_prospective_shadow(
            confirmation(),summary
        )
        self.assertEqual(
            gate["kind"],
            "KALSHI_PROSPECTIVE_SHADOW_GATE_NO_ORDER",
        )
        self.assertTrue(gate["prospective_or_shadow_complete"])
        self.assertEqual(
            gate["candidates_passing_prospective_shadow"],
            [CANDIDATE],
        )
        self.assertFalse(gate["candidate_ranking_performed"])
        self.assertEqual(gate["automatic_candidate_selection"],"DISABLED")
        self.assertEqual(gate["demo_order_submission"],"DISABLED")
        self.assertEqual(gate["live_order_submission"],"DISABLED")
        self.assertFalse(
            gate["historical_data_substituted_for_prospective_evidence"]
        )

    def test_pending_or_fewer_than_twenty_valid_markets_blocks_summary(self):
        with self.assertRaises(ValueError):
            build_kalshi_prospective_shadow_summary(
                confirmation(),audit(pending=1)
            )
        with self.assertRaises(ValueError):
            build_kalshi_prospective_shadow_summary(
                confirmation(),audit(valid=19,missed=1)
            )

    def test_unconfirmed_candidate_cannot_be_added_from_future_outcomes(self):
        bad=confirmation("not-a-predeclared-strategy")
        with self.assertRaises(ValueError):
            build_kalshi_prospective_shadow_summary(bad,audit())

    def test_audit_with_backfill_or_post_settlement_decision_is_refused(self):
        for key,value in (
            ("historical_backfill_count",1),
            ("post_settlement_decision_count",1),
            ("outcome_direction_used_for_market_selection",True),
        ):
            evidence=audit()
            evidence[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                build_kalshi_prospective_shadow_summary(
                    confirmation(),evidence
                )


if __name__=="__main__":
    unittest.main()

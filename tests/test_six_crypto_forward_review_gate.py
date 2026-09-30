"""Forward review gate is frozen before outcomes and cannot authorize orders."""
from __future__ import annotations

import unittest
from dataclasses import replace
from decimal import Decimal

from signal_vault.six_crypto_forward_review_gate import (
    BASE_SCENARIO,HIGH_SCENARIO,ForwardReviewPolicy,
    assess_forward_review_gate,
)

CASH="cash-v1-predeclared"
PASSIVE="one-allocation-passive-v1-predeclared"
EMA="generic-ema12x26-v1-predeclared"
MOM="generic-momentum24bar50bps-v1-predeclared"


def one(pnl,*,fills=12,drawdown="2",halt=False,scored=168):
    return {
        "net_pnl_if_hypothetically_liquidated_usd":str(pnl),
        "sampled_event_max_drawdown_usd":str(drawdown),
        "synthetic_fill_count":fills,
        "evaluated_precommitted_outcome_intervals":scored,
        "persistent_peak_drawdown_entry_halt":halt,
        "broker_order_submission":"DISABLED",
    }


def complete_scorecard(*,ema_base="3",ema_high="1",mom_base="4",
                       mom_high="2",passive_base="1",passive_high="0.5",
                       fills=12,drawdown="2",halt=False,
                       source=169,scored=168):
    def case(active_ema,active_mom,passive):
        return {
            "fixed_predeclared_hypotheses":{
                CASH:one("0",fills=0,drawdown="0",scored=scored),
                PASSIVE:one(passive,fills=2,drawdown="1",scored=scored),
                EMA:one(active_ema,fills=fills,drawdown=drawdown,
                        halt=halt,scored=scored),
                MOM:one(active_mom,fills=fills,drawdown=drawdown,
                        halt=halt,scored=scored),
            }
        }
    return {
        "kind":"OFFLINE_SIX_CRYPTO_PROSPECTIVE_SHADOW_SCORECARD",
        "status":"FULL_168_PRECOMMITTED_DECISION_OUTCOMES_AVAILABLE",
        "current_segment_prospective_source_hours":source,
        "fully_observed_precommitted_decision_intervals":scored,
        "broker_order_submission":"DISABLED",
        "strategy_promoted":False,
        "future_edge_established":False,
        "scenarios":{
            "illustrative_low_friction":case("4","5","1.2"),
            BASE_SCENARIO:case(ema_base,mom_base,passive_base),
            HIGH_SCENARIO:case(ema_high,mom_high,passive_high),
        },
    }


class PredeclaredSixCryptoForwardReviewGateTests(unittest.TestCase):
    def test_incomplete_forward_window_is_waiting_not_promotion(self):
        score=complete_scorecard(source=0,scored=0)
        result=assess_forward_review_gate(score)
        self.assertFalse(result["evidence_window_complete_for_gate"])
        self.assertEqual(result["candidates_meeting_all_review_criteria"],[])
        for candidate in (EMA,MOM):
            assessed=result["active_candidate_assessments"][candidate]
            self.assertFalse(assessed["criteria_met"])
            self.assertFalse(
                assessed["owner_paper_execution_design_review_eligible"])
            self.assertIn("minimum_169_source_hours",
                          assessed["failed_criteria"])
            self.assertIn(
                "minimum_168_fully_observed_precommitted_outcomes",
                assessed["failed_criteria"])
        for comparator in (CASH,PASSIVE):
            self.assertFalse(result["comparators"][comparator][
                "owner_paper_execution_design_review_eligible"])
        self.assertEqual(result["paper_order_submission"],"DISABLED")
        self.assertTrue(result[
            "separate_owner_authorization_still_required_for_any_PAPER_execution"])

    def test_complete_good_candidates_meet_same_fixed_criteria_without_ranking(self):
        result=assess_forward_review_gate(complete_scorecard())
        self.assertTrue(result["evidence_window_complete_for_gate"])
        self.assertEqual(
            result["candidates_meeting_all_review_criteria"],
            sorted([EMA,MOM]))
        self.assertTrue(result["candidate_order_has_no_rank_or_preference"])
        self.assertEqual(result["automatic_candidate_selection"],"DISABLED")
        for candidate in (EMA,MOM):
            item=result["active_candidate_assessments"][candidate]
            self.assertTrue(item["criteria_met"])
            self.assertEqual(item["failed_criteria"],[])
            self.assertTrue(item[
                "owner_paper_execution_design_review_eligible"])
            self.assertEqual(item["broker_order_submission"],"DISABLED")
        self.assertTrue(result["passing_does_not_establish_future_profit"])
        self.assertEqual(result["live_trading"],"UNAVAILABLE")

    def test_high_friction_loss_or_failure_to_beat_passive_blocks_only_criteria(self):
        score=complete_scorecard(
            ema_high="-0.01",mom_high="0.4",passive_high="0.5")
        result=assess_forward_review_gate(score)
        ema=result["active_candidate_assessments"][EMA]
        mom=result["active_candidate_assessments"][MOM]
        self.assertIn("high_exit_inclusive_pnl_positive",
                      ema["failed_criteria"])
        self.assertIn("high_outperforms_same_book_passive",
                      ema["failed_criteria"])
        self.assertNotIn("high_exit_inclusive_pnl_positive",
                         mom["failed_criteria"])
        self.assertIn("high_outperforms_same_book_passive",
                      mom["failed_criteria"])
        self.assertEqual(result["candidates_meeting_all_review_criteria"],[])

    def test_too_few_fills_drawdown_or_peak_halt_fail_without_orders(self):
        cases=(
            complete_scorecard(fills=9),
            complete_scorecard(drawdown="10.01"),
            complete_scorecard(halt=True),
        )
        expected=(
            "minimum_10_base_synthetic_fills",
            "base_sampled_drawdown_at_or_below_10_usd",
            "base_no_persistent_peak_drawdown_halt",
        )
        for score,reason in zip(cases,expected):
            with self.subTest(reason=reason):
                result=assess_forward_review_gate(score)
                for candidate in (EMA,MOM):
                    self.assertIn(
                        reason,
                        result["active_candidate_assessments"][candidate][
                            "failed_criteria"])
                    self.assertFalse(result[
                        "active_candidate_assessments"][candidate][
                            "owner_paper_execution_design_review_eligible"])
                self.assertEqual(result["paper_order_submission"],"DISABLED")

    def test_passive_and_cash_are_permanent_comparators_not_candidates(self):
        result=assess_forward_review_gate(
            complete_scorecard(passive_base="100",passive_high="100"))
        self.assertEqual(set(result["comparators"]),{CASH,PASSIVE})
        self.assertNotIn(PASSIVE,result["active_candidate_assessments"])
        self.assertNotIn(CASH,result["active_candidate_assessments"])
        self.assertFalse(result["comparators"][PASSIVE][
            "owner_paper_execution_design_review_eligible"])
        self.assertEqual(result["candidates_meeting_all_review_criteria"],[])

    def test_source_claiming_orders_or_edge_is_rejected_before_gate(self):
        for field,value in (
            ("broker_order_submission","ENABLED"),
            ("strategy_promoted",True),
            ("future_edge_established",True),
        ):
            score=complete_scorecard()
            score[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                assess_forward_review_gate(score)

    def test_impossible_scored_count_and_missing_scenario_fail_closed(self):
        with self.assertRaises(ValueError):
            assess_forward_review_gate(
                complete_scorecard(source=169,scored=169))
        score=complete_scorecard()
        score["scenarios"].pop(HIGH_SCENARIO)
        with self.assertRaises(ValueError):
            assess_forward_review_gate(score)

    def test_v1_policy_thresholds_cannot_be_tuned_in_place(self):
        for change in (
            {"minimum_prospective_source_hours":168},
            {"minimum_fully_scored_outcomes":167},
            {"minimum_base_synthetic_fills":9},
            {"maximum_sampled_drawdown_usd":Decimal("11")},
            {"policy_version":"changed-after-outcomes"},
        ):
            with self.subTest(change=change),self.assertRaises(ValueError):
                ForwardReviewPolicy(**change)


if __name__=="__main__":
    unittest.main()

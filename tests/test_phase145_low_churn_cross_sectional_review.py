from decimal import Decimal
from pathlib import Path
import unittest
from unittest.mock import patch

from signal_vault import cross_sectional_crypto_review as review


def result(pnl="2", passive="1", fills=4, dd="1"):
    return {
        "net_marked_pnl_usd":pnl,
        "passive_equal_weight_marked_pnl_usd":passive,
        "fill_count":fills,
        "max_marked_drawdown_usd":dd,
    }


class Phase145LowChurnReviewTests(unittest.TestCase):
    def fake_load(self,_folder):
        return ({s:tuple() for s in review.SYMBOLS},2160)

    def test_exactly_one_candidate_can_freeze_without_paper_activation(self):
        calls=[]
        def sim(_data,*,config,evaluation_start_index,evaluation_end_index):
            calls.append((config.top_n,evaluation_start_index,evaluation_end_index))
            if config.top_n==1:
                return result()
            return result(pnl="-1")
        with patch.object(review,"_load",self.fake_load), patch.object(
            review,"simulate_cross_sectional_strength",side_effect=sim):
            out=review.build_review(Path("unused"))
        self.assertEqual(
            out["status"],
            "ONE_LOW_CHURN_CANDIDATE_FROZEN_FOR_NEW_PROSPECTIVE_CONFIRMATION",
        )
        self.assertEqual(
            out["selected_strategy"],
            "cross-sectional-top1-168h-250bps-weekly-v1-predeclared",
        )
        self.assertFalse(out["paper_activation_permitted"])
        self.assertTrue(out["new_prospective_confirmation_required"])
        self.assertTrue(out["historical_holdout_never_selects_or_vetoes"])

    def test_multiple_candidates_block_without_ranking(self):
        with patch.object(review,"_load",self.fake_load), patch.object(
            review,"simulate_cross_sectional_strength",return_value=result()):
            out=review.build_review(Path("unused"))
        self.assertEqual(out["status"],"BLOCKED_MULTIPLE_LOW_CHURN_CANDIDATES_NO_RANKING")
        self.assertIsNone(out["selected_strategy"])
        self.assertEqual(out["automatic_strategy_ranking"],"DISABLED")

    def test_no_candidate_blocks(self):
        with patch.object(review,"_load",self.fake_load), patch.object(
            review,"simulate_cross_sectional_strength",
            return_value=result(pnl="-2",passive="1")):
            out=review.build_review(Path("unused"))
        self.assertEqual(out["status"],"BLOCKED_NO_LOW_CHURN_CANDIDATE")
        self.assertIsNone(out["selected_strategy"])


if __name__=="__main__":
    unittest.main()

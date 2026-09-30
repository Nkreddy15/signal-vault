import unittest

from signal_vault.historical_validation_plan import (
    chronological_split,
    expanding_walk_forward,
    market_validation_contract,
)


class HistoricalValidationPlanTests(unittest.TestCase):
    def test_three_way_split_is_strictly_chronological(self):
        source=tuple(range(100))
        result=chronological_split(source,warmup_count=10)
        self.assertEqual(result["warmup"],tuple(range(10)))
        self.assertEqual(result["train"][0],10)
        self.assertLess(result["train"][-1],result["validation"][0])
        self.assertLess(result["validation"][-1],result["untouched_test"][0])
        self.assertEqual(result["counts"]["total"],100)
        self.assertFalse(result["test_period_used_for_strategy_selection"])
        self.assertTrue(result["historical_data_is_not_prospective_validation"])
        self.assertEqual(result["broker_order_submission"],"DISABLED")

    def test_expanding_walk_forward_never_trains_on_future_validation(self):
        source=tuple(range(60))
        folds=expanding_walk_forward(
            source,initial_train_count=20,validation_count=5,step_count=5
        )
        self.assertGreater(len(folds),1)
        for fold in folds:
            self.assertLess(max(fold["train"]),min(fold["validation"]))
            self.assertTrue(fold["strictly_past_trains_future_validation"])

    def test_market_contract_never_promotes_historical_data_to_live(self):
        source=tuple(range(100))
        split=chronological_split(source,warmup_count=10)
        folds=expanding_walk_forward(
            source[10:],initial_train_count=30,validation_count=10,step_count=10
        )
        for lane in ("crypto","us_equity","kalshi_event_contract"):
            result=market_validation_contract(
                market_lane=lane,
                observation_count=100,
                split=split,
                walk_forward_fold_count=len(folds),
            )
            self.assertFalse(result["historical_validation_complete"])
            self.assertTrue(result["requires_separate_prospective_or_paper_validation"])
            self.assertEqual(result["automatic_strategy_promotion"],"DISABLED")
            self.assertEqual(result["live_trading"],"UNAVAILABLE")

    def test_small_or_invalid_windows_fail_closed(self):
        with self.assertRaises(ValueError):
            chronological_split(tuple(range(10)))
        with self.assertRaises(ValueError):
            expanding_walk_forward(
                tuple(range(10)),initial_train_count=5,validation_count=2,step_count=1
            )
        with self.assertRaises(ValueError):
            market_validation_contract(
                market_lane="forex",
                observation_count=20,
                split={"counts":{"total":20}},
                walk_forward_fold_count=1,
            )


if __name__=="__main__":
    unittest.main()

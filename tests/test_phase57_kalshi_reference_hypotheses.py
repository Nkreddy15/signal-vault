import unittest

from signal_vault.kalshi_reference_hypotheses import (
    HYPOTHESES,
    POLICY_VERSION,
    frozen_hypothesis_receipt,
    reference_decision,
)


class KalshiReferenceHypothesesTests(unittest.TestCase):
    def by_name(self,name):
        return next(x for x in HYPOTHESES if x.name==name)

    def test_hypotheses_are_unique_frozen_and_no_order(self):
        receipt=frozen_hypothesis_receipt()
        names=[x["name"] for x in receipt["hypotheses"]]
        self.assertEqual(len(names),len(set(names)))
        self.assertEqual(receipt["policy_version"],POLICY_VERSION)
        self.assertFalse(receipt["outcome_used_to_make_entry_decision"])
        self.assertFalse(
            receipt["historical_strategy_results_used_to_define_hypotheses"]
        )
        self.assertEqual(receipt["hyperparameter_optimization"],"DISABLED")
        self.assertEqual(receipt["automatic_strategy_selection"],"DISABLED")
        self.assertEqual(receipt["demo_order_submission"],"DISABLED")
        self.assertEqual(receipt["live_order_submission"],"DISABLED")

    def test_market_favorite_and_contrarian_are_deterministic_without_outcome(self):
        fav=self.by_name("market-favorite-6h-hold-v1-predeclared")
        contra=self.by_name("market-contrarian-6h-hold-v1-predeclared")
        self.assertEqual(
            reference_decision(fav,yes_trade_probability="0.60")["action"],
            "buy_yes",
        )
        self.assertEqual(
            reference_decision(fav,yes_trade_probability="0.40")["action"],
            "buy_no",
        )
        self.assertEqual(
            reference_decision(contra,yes_trade_probability="0.60")["action"],
            "buy_no",
        )
        self.assertEqual(
            reference_decision(contra,yes_trade_probability="0.40")["action"],
            "buy_yes",
        )
        for hypothesis in (fav,contra):
            decision=reference_decision(
                hypothesis,yes_trade_probability="0.60"
            )
            self.assertFalse(decision["final_outcome_accessed"])
            self.assertFalse(decision["historical_pnl_accessed"])
            self.assertEqual(decision["order_submission"],"DISABLED")

    def test_cash_missing_price_and_tie_never_manufacture_trade(self):
        cash=self.by_name("cash-v1-predeclared")
        fav=self.by_name("market-favorite-24h-hold-v1-predeclared")
        self.assertEqual(
            reference_decision(cash,yes_trade_probability="0.99")["action"],
            "hold",
        )
        self.assertEqual(
            reference_decision(fav,yes_trade_probability=None)["action"],
            "hold",
        )
        self.assertEqual(
            reference_decision(fav,yes_trade_probability="0.5")["action"],
            "hold",
        )

    def test_out_of_range_probability_fails_closed(self):
        fav=self.by_name("market-favorite-6h-hold-v1-predeclared")
        for value in ("-0.01","1.01","nan"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                reference_decision(fav,yes_trade_probability=value)


if __name__=="__main__":
    unittest.main()

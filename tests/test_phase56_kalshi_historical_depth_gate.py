import unittest

from signal_vault.kalshi_historical_depth_gate import (
    POLICY_VERSION,
    assess_kalshi_historical_depth,
)


def corpus(*, total=50, yes=25, no=25, coverage=None):
    coverage=coverage or {86400:"0.80",21600:"0.90",3600:"0.92"}
    return {
        "kind":"OFFLINE_KALSHI_RESOLVED_CORPUS_CALIBRATION_REPORT",
        "resolved_market_count":total,
        "yes_outcome_count":yes,
        "no_outcome_count":no,
        "fixed_horizon_summary":{
            str(h):{
                "horizon_seconds_before_settlement":h,
                "available_market_count":int(total*float(v)),
                "missing_market_count":total-int(total*float(v)),
                "coverage_fraction":v,
                "mean_brier_error":"0.20",
                "mean_yes_probability":"0.50",
            } for h,v in coverage.items()
        },
        "historical_corpus_is_not_prospective_validation":True,
        "market_price_calibration_is_not_strategy_alpha":True,
        "strategy_ranking_performed":False,
        "strategy_selection_performed":False,
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
    }


class KalshiHistoricalDepthGateTests(unittest.TestCase):
    def test_predeclared_depth_pass_does_not_authorize_execution(self):
        result=assess_kalshi_historical_depth(corpus())
        self.assertEqual(result["policy_version"],POLICY_VERSION)
        self.assertTrue(
            result["historical_depth_ready_for_fixed_strategy_research"]
        )
        self.assertEqual(
            result["next_action"],
            "DEFINE_AND_FREEZE_KALSHI_STRATEGY_BEFORE_STRATEGY_SCORING",
        )
        self.assertFalse(result["brier_error_used_to_set_depth_gate"])
        self.assertFalse(result["historical_pnl_used_to_set_depth_gate"])
        self.assertFalse(result["strategy_results_used_to_set_depth_gate"])
        self.assertFalse(result["demo_execution_eligible"])
        self.assertFalse(result["paper_execution_eligible"])
        self.assertFalse(result["live_execution_eligible"])
        self.assertEqual(result["order_submission"],"DISABLED")

    def test_small_or_imbalanced_or_sparse_corpus_fails(self):
        cases=(
            corpus(total=49,yes=25,no=24),
            corpus(total=50,yes=45,no=5),
            corpus(coverage={86400:"0.59",21600:"0.90",3600:"0.90"}),
            corpus(coverage={86400:"0.80",21600:"0.79",3600:"0.90"}),
            corpus(coverage={86400:"0.80",21600:"0.90",3600:"0.79"}),
        )
        for item in cases:
            with self.subTest(item=item):
                result=assess_kalshi_historical_depth(item)
                self.assertFalse(
                    result["historical_depth_ready_for_fixed_strategy_research"]
                )
                self.assertEqual(
                    result["next_action"],
                    "COLLECT_MORE_DETERMINISTIC_RESOLVED_MARKET_EVIDENCE",
                )
                self.assertFalse(result["demo_execution_eligible"])

    def test_inconsistent_outcome_and_coverage_counts_fail_closed(self):
        bad=corpus()
        bad["yes_outcome_count"]=30
        with self.assertRaises(ValueError):
            assess_kalshi_historical_depth(bad)

        bad=corpus()
        bad["fixed_horizon_summary"]["86400"]["available_market_count"]=1
        with self.assertRaises(ValueError):
            assess_kalshi_historical_depth(bad)


if __name__=="__main__":
    unittest.main()

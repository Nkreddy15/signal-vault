import unittest

from signal_vault.offline_kalshi_corpus_validation import (
    aggregate_resolved_market_scores,
)


def score(ticker,result,digest,rows):
    return {
        "kind":"OFFLINE_KALSHI_RESOLVED_MARKET_CALIBRATION_SCORE",
        "ticker":ticker,
        "resolved_result":result,
        "source_manifest_sha256":digest,
        "fixed_horizon_scores":rows,
        "historical_data_is_not_prospective_validation":True,
        "score_is_market_price_calibration_not_strategy_alpha":True,
        "strategy_selection_performed":False,
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
    }


def row(h,p,b):
    return {
        "horizon_seconds_before_settlement":h,
        "observation_available":p is not None,
        "yes_probability":p,
        "brier_error":b,
        "candle_end_ts":None if p is None else 100,
    }


class KalshiResolvedCorpusValidationTests(unittest.TestCase):
    def test_unique_binary_markets_are_aggregated_without_strategy_selection(self):
        horizons=(86400,21600,3600)
        scores=[
            score("A","yes","a"*64,[
                row(86400,"0.40","0.36"),
                row(21600,"0.60","0.16"),
                row(3600,"0.80","0.04"),
            ]),
            score("B","no","b"*64,[
                row(86400,"0.30","0.09"),
                row(21600,"0.20","0.04"),
                row(3600,None,None),
            ]),
        ]
        result=aggregate_resolved_market_scores(
            scores,horizons_seconds=horizons
        )
        self.assertEqual(result["resolved_market_count"],2)
        self.assertEqual(result["yes_outcome_count"],1)
        self.assertEqual(result["no_outcome_count"],1)
        one_day=result["fixed_horizon_summary"]["86400"]
        self.assertEqual(one_day["available_market_count"],2)
        self.assertEqual(one_day["coverage_fraction"],"1")
        self.assertEqual(one_day["mean_brier_error"],"0.225")
        one_hour=result["fixed_horizon_summary"]["3600"]
        self.assertEqual(one_hour["available_market_count"],1)
        self.assertEqual(one_hour["coverage_fraction"],"0.5")
        self.assertFalse(result["strategy_ranking_performed"])
        self.assertFalse(result["strategy_selection_performed"])
        self.assertTrue(result["market_price_calibration_is_not_strategy_alpha"])
        self.assertEqual(result["demo_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")

    def test_duplicate_market_or_manifest_is_rejected(self):
        base=score("A","yes","a"*64,[
            row(86400,"0.4","0.36"),
        ])
        duplicate_ticker=score("A","no","b"*64,[
            row(86400,"0.3","0.09"),
        ])
        duplicate_manifest=score("B","no","a"*64,[
            row(86400,"0.3","0.09"),
        ])
        for second in (duplicate_ticker,duplicate_manifest):
            with self.subTest(second=second["ticker"]), self.assertRaises(ValueError):
                aggregate_resolved_market_scores(
                    [base,second],horizons_seconds=(86400,)
                )

    def test_child_horizon_mismatch_and_fabricated_missing_score_fail_closed(self):
        missing_horizon=score("A","yes","a"*64,[
            row(86400,"0.4","0.36"),
        ])
        with self.assertRaises(ValueError):
            aggregate_resolved_market_scores(
                [missing_horizon],horizons_seconds=(86400,3600)
            )
        fabricated=score("B","no","b"*64,[{
            "horizon_seconds_before_settlement":86400,
            "observation_available":False,
            "yes_probability":"0.2",
            "brier_error":None,
            "candle_end_ts":None,
        }])
        with self.assertRaises(ValueError):
            aggregate_resolved_market_scores(
                [fabricated],horizons_seconds=(86400,)
            )


if __name__=="__main__":
    unittest.main()

import unittest

from signal_vault.long_horizon_crypto_candidate_review import (
    BLOCKED_KIND,
    OUTPUT_KIND,
    build_long_horizon_candidate_review,
)

SYMBOLS=["AVAX/USD","BTC/USD","ETH/USD","LINK/USD","LTC/USD","SOL/USD"]
EMA="generic-ema12x26-v1-predeclared"
CONF="generic-ema12x26-confirm2-v2-predeclared"
MOM="generic-momentum24bar50bps-v1-predeclared"
SCENARIOS=[
    "illustrative_low_friction",
    "illustrative_base_friction",
    "illustrative_high_friction",
]


def fold(pnl="2",passive="1",fills=2,dd="1"):
    return {
        "net_marked_pnl_usd":pnl,
        "passive_same_allocation_marked_pnl_usd":passive,
        "fill_count":fills,
        "max_marked_drawdown_usd":dd,
    }


def offline_report(*,winner=EMA,test_pnl="2",second_winner=False):
    per={}
    for sym in SYMBOLS:
        per[sym]={}
        for strat in (EMA,CONF,MOM):
            good=strat==winner or (second_winner and strat==CONF)
            per[sym][strat]={
                "development":fold("2","1",2,"1") if good else fold("-1","0",2,"1"),
                "validation":fold("2","1",2,"1") if good else fold("-1","0",2,"1"),
                "untouched_test":fold(test_pnl,"1",2,"1") if strat==winner else fold("-1","0",2,"1"),
            }
    return {"per_asset_disjoint_chronological_folds":per}


def analysis(*,hours=2160,test_pnl="2",second_winner=False):
    from datetime import datetime,timedelta,timezone
    start=datetime(2026,6,27,18,tzinfo=timezone.utc)
    end=start+timedelta(hours=hours)
    scenarios={
        s:{
            "offline_report":offline_report(
                test_pnl=test_pnl,
                second_winner=second_winner,
            )
        }
        for s in SCENARIOS
    }
    return {
        "kind":"HISTORICAL_MULTIASSET_SHA_BOUND_THREE_COST_SCENARIOS_NO_ORDERS",
        "market":"crypto",
        "symbols":SYMBOLS,
        "predeclared_request_windows":[{
            "start_utc":start.isoformat(),
            "end_utc":end.isoformat(),
        }],
        "scenarios":scenarios,
        "data_is_historical_not_new_prospective_observations":True,
        "candidate_selection_from_untouched_test":False,
        "strategy_promoted":False,
        "network_requests_during_analysis":"NONE",
        "credential_access_during_analysis":"NONE",
        "broker_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


class LongHorizonCryptoCandidateReviewTests(unittest.TestCase):
    def test_exact_90_day_one_candidate_can_be_frozen_for_later_confirmation(self):
        result=build_long_horizon_candidate_review(analysis())
        self.assertEqual(result["kind"],OUTPUT_KIND)
        self.assertEqual(result["selected_strategy"],EMA)
        self.assertTrue(result["six_day_confirmation_still_required"])
        self.assertFalse(result["paper_activation_permitted"])
        self.assertEqual(result["paper_order_submission"],"DISABLED")
        self.assertEqual(result["live_trading"],"UNAVAILABLE")

    def test_non_90_day_window_blocks(self):
        result=build_long_horizon_candidate_review(analysis(hours=144))
        self.assertEqual(result["kind"],BLOCKED_KIND)
        self.assertEqual(
            result["status"],
            "BLOCKED_LONG_HORIZON_NOT_EXACTLY_90_DAYS",
        )

    def test_untouched_test_can_only_veto(self):
        result=build_long_horizon_candidate_review(analysis(test_pnl="-1"))
        self.assertEqual(result["kind"],BLOCKED_KIND)
        self.assertEqual(
            result["status"],
            "BLOCKED_LONG_HORIZON_UNTOUCHED_TEST_VETO",
        )
        self.assertEqual(result["selected_strategy"],EMA)

    def test_multiple_supported_candidates_block_without_ranking(self):
        result=build_long_horizon_candidate_review(analysis(second_winner=True))
        self.assertEqual(result["kind"],BLOCKED_KIND)
        self.assertEqual(
            result["status"],
            "BLOCKED_MULTIPLE_LONG_HORIZON_CANDIDATES_NO_RANKING",
        )
        self.assertIsNone(result["selected_strategy"])


if __name__=="__main__":
    unittest.main()

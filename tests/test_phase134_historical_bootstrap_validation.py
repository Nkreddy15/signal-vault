import unittest

from signal_vault.historical_bootstrap_validation import (
    BLOCKED_KIND,
    OUTPUT_KIND,
    build_historical_bootstrap_validation,
)


SYMBOLS=["AVAX/USD","BTC/USD","ETH/USD","LINK/USD","LTC/USD","SOL/USD"]
EMA="generic-ema12x26-v1-predeclared"
MOM="generic-momentum24bar50bps-v1-predeclared"
SCENARIOS=[
    "illustrative_low_friction",
    "illustrative_base_friction",
    "illustrative_high_friction",
]


def fold(pnl,passive,fills,dd):
    return {
        "evaluation_start_utc":"2026-09-25T00:00:00+00:00",
        "evaluation_end_utc":"2026-10-01T00:00:00+00:00",
        "net_marked_pnl_usd":str(pnl),
        "passive_same_allocation_marked_pnl_usd":str(passive),
        "max_marked_drawdown_usd":str(dd),
        "estimated_fees_usd":"0.1",
        "fill_count":fills,
        "data_sha256":"a"*64,
    }


def report(*,ema_validation="2",ema_test="1",mom_validation="-1"):
    per={}
    for sym in SYMBOLS:
        per[sym]={
            EMA:{
                "development":fold("1","0",2,"1"),
                "validation":fold(ema_validation,"0.5",2,"2"),
                "untouched_test":fold(ema_test,"0.2",2,"2"),
            },
            MOM:{
                "development":fold("0","0",1,"1"),
                "validation":fold(mom_validation,"0.5",1,"2"),
                "untouched_test":fold("1","0.2",2,"2"),
            },
            "cash-v1-predeclared":{
                "development":fold("0","0",0,"0"),
                "validation":fold("0","0",0,"0"),
                "untouched_test":fold("0","0",0,"0"),
            },
            "one-allocation-passive-v1-predeclared":{
                "development":fold("0","0",1,"1"),
                "validation":fold("0","0",1,"1"),
                "untouched_test":fold("0","0",1,"1"),
            },
        }
    return {
        "asset_quality_reviews":{},
        "historical_archive_count":1,
        "predeclared_hypotheses":[
            "cash-v1-predeclared",
            "one-allocation-passive-v1-predeclared",
            EMA,
            MOM,
        ],
        "per_asset_disjoint_chronological_folds":per,
        "one_SHARED_100_usd_portfolio_by_fixed_hypothesis":{},
        "strategy_chosen_from_validation_or_test":False,
        "simulation_accounting_version":
            "v2_utc_daily_reset_plus_persistent_peak_drawdown_halt",
    }


def analysis(*,hours=144,ema_test="1"):
    start="2026-09-25T00:00:00+00:00"
    end="2026-10-01T00:00:00+00:00"
    if hours!=144:
        end="2026-09-29T00:00:00+00:00"
    scenarios={
        s:{
            "assumptions_per_instrument":{},
            "estimated_not_observed_fees_and_spreads":True,
            "offline_report":report(ema_test=ema_test),
        }
        for s in SCENARIOS
    }
    return {
        "kind":"HISTORICAL_MULTIASSET_SHA_BOUND_THREE_COST_SCENARIOS_NO_ORDERS",
        "schema_version":1,
        "market":"crypto",
        "symbols":SYMBOLS,
        "predeclared_request_windows":[{"start_utc":start,"end_utc":end}],
        "historical_archive_audit":[],
        "completed_historical_windows":1,
        "scenarios":scenarios,
        "data_is_historical_not_new_prospective_observations":True,
        "independent_forward_strategy_edge_established":False,
        "simulation_accounting_version":
            "v2_utc_daily_reset_plus_persistent_peak_drawdown_halt",
        "previous_v1_historical_outputs_are_not_directly_comparable":True,
        "candidate_selection_from_untouched_test":False,
        "strategy_promoted":False,
        "network_requests_during_analysis":"NONE",
        "credential_access_during_analysis":"NONE",
        "broker_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


class HistoricalBootstrapValidationTests(unittest.TestCase):
    def test_validation_selects_one_candidate_then_test_only_vetoes(self):
        result=build_historical_bootstrap_validation(analysis())
        self.assertEqual(result["kind"],OUTPUT_KIND)
        self.assertEqual(result["selected_strategy"],EMA)
        self.assertEqual(result["historical_hours"],144)
        self.assertTrue(result["selection_used_validation_only"])
        self.assertTrue(result["untouched_test_used_only_as_veto"])
        self.assertFalse(result["test_used_for_tuning"])
        self.assertTrue(all(result["cost_stress_passes"].values()))
        self.assertEqual(len(result["receipt_sha256"]),64)
        self.assertEqual(result["broker_order_submission"],"DISABLED")
        self.assertEqual(result["live_trading"],"UNAVAILABLE")

    def test_untouched_test_can_veto_but_cannot_select_other_candidate(self):
        result=build_historical_bootstrap_validation(analysis(ema_test="-1"))
        self.assertEqual(result["kind"],BLOCKED_KIND)
        self.assertEqual(result["status"],"BLOCKED_UNTOUCHED_TEST_VETO")
        self.assertEqual(result["selected_strategy"],EMA)
        self.assertTrue(result["selection_used_validation_only"])

    def test_short_history_is_blocked(self):
        result=build_historical_bootstrap_validation(analysis(hours=120-24))
        self.assertEqual(result["kind"],BLOCKED_KIND)
        self.assertEqual(result["status"],"BLOCKED_HISTORY_WINDOW_NOT_5_TO_7_DAYS")

    def test_multiple_validation_candidates_block_without_ranking(self):
        value=analysis()
        for wrapper in value["scenarios"].values():
            for sym in SYMBOLS:
                wrapper["offline_report"]["per_asset_disjoint_chronological_folds"][sym][MOM]["validation"]=fold("2","0.5",2,"2")
        result=build_historical_bootstrap_validation(value)
        self.assertEqual(result["kind"],BLOCKED_KIND)
        self.assertEqual(
            result["status"],
            "BLOCKED_MULTIPLE_VALIDATION_CANDIDATES_NO_RANKING",
        )
        self.assertIsNone(result["selected_strategy"])


if __name__=="__main__":
    unittest.main()

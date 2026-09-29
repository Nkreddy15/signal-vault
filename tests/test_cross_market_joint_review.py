"""All 12 predeclared mixed-market sources; no prospective/trading claims."""
from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from decimal import Decimal

from signal_vault.cross_market_joint_review import (
    CRYPTO_SIX,STOCK_SIX,evaluate_predeclared_twelve_market_common_history,
)
from signal_vault.research_universe import ResearchBar

UTC=timezone.utc
HOUR=timedelta(hours=1)
AS_OF=datetime(2026,9,26,tzinfo=UTC)
CRYPTO_START=datetime(2026,9,14,tzinfo=UTC)
STOCK_START=datetime(2026,9,14,14,tzinfo=UTC)
STOCK_DAYS=(0,1,2,3,4,7,8,9,10,11)
STOCK_GRID=tuple(STOCK_START+timedelta(days=d,hours=i)
                 for d in STOCK_DAYS for i in range(6))


def generated(sym,times,px,source,as_of=AS_OF):
    val=Decimal(px)
    return tuple(ResearchBar(
        sym,t,val,val+Decimal("2"),val-Decimal("2"),val,
        Decimal("50"),source,as_of,False)
        for t in times)


def datasets(crypto_start=CRYPTO_START,crypto_hours=288):
    crypto_times=tuple(crypto_start+i*HOUR for i in range(crypto_hours))
    return (
        {sym:generated(sym,crypto_times,str(100+10*i),
                       "synthetic_crypto_data_only")
         for i,sym in enumerate(CRYPTO_SIX)},
        {sym:generated(sym,STOCK_GRID,str(200+50*i),
                       "synthetic_iex_adjustment_all")
         for i,sym in enumerate(STOCK_SIX)},
    )


class TwelveMarketCommonResearchTests(unittest.TestCase):
    def test_all_twelve_hypotheses_stress_one_SHARED_100_after_stock_warmup(self):
        crypto,equity=datasets()
        result=evaluate_predeclared_twelve_market_common_history(
            crypto=crypto,equities=equity,
            independently_verified_stock_core_opens_utc=STOCK_GRID,
            as_of=AS_OF)
        self.assertEqual(len(result["twelve_source_data_sha256"]),12)
        self.assertEqual(len(result["crypto_symbols"]),6)
        self.assertEqual(len(result["stock_symbols"]),6)
        self.assertEqual(
            result["stock_and_crypto_time_compatibility"][
                "common_source_closed_bar_open_hours"],60)
        self.assertEqual(result["evaluated_stock_regular_CORE_hour_opens_after_global_warmup"],32)
        self.assertEqual(result["common_research_start_utc"],
                         datetime(2026,9,18,18,tzinfo=UTC).isoformat())
        self.assertEqual(result["common_research_end_utc_exclusive"],
                         datetime(2026,9,25,20,tzinfo=UTC).isoformat())
        self.assertTrue(result["one_SHARED_100_usd_cash_not_twelve_times_100"])
        self.assertEqual(result["max_combined_long_exposure_usd"],"30")
        self.assertEqual(result["network_requests"],"NONE")
        self.assertEqual(result["broker_order_submission"],"DISABLED")
        self.assertFalse(result["future_edge_established"])
        self.assertFalse(result["no_strategy_chosen_from_test_results"] is False)
        self.assertEqual(len(result["three_estimated_friction_scenarios"]),3)
        for label,scenario in result["three_estimated_friction_scenarios"].items():
            self.assertEqual(len(scenario["predeclared_hypothesis_results"]),4)
            for h,study in scenario["predeclared_hypothesis_results"].items():
                self.assertEqual(study["initial_SHARED_bankroll_usd"],"100")
                self.assertEqual(study["combined_12_market_exposure_cap_usd"],"30")
                self.assertEqual(study["actual_order_submissions"],0)
                self.assertEqual(study["broker_order_submission"],"DISABLED")
                self.assertTrue(all(
                    datetime.fromisoformat(f["at_open_utc"]) >=
                    datetime(2026,9,18,18,tzinfo=UTC)
                    for f in study["synthetic_fills"]))
            baseline=scenario["predeclared_hypothesis_results"][
                "cash-v1-predeclared"]
            self.assertEqual(baseline["hypothetical_exit_inclusive_pnl_usd"],"0")
        self.assertEqual(
            result,evaluate_predeclared_twelve_market_common_history(
                crypto=crypto,equities=equity,
                independently_verified_stock_core_opens_utc=STOCK_GRID,
                as_of=AS_OF))

    def test_disjoint_real_history_sept_stocks_vs_july_aug_crypto_fails_before_pnl(self):
        crypto,equity=datasets(
            crypto_start=datetime(2026,8,20,tzinfo=UTC),
            crypto_hours=288)
        with self.assertRaisesRegex(ValueError,"NO_VALID_TWELVE_ASSET_COMMON"):
            evaluate_predeclared_twelve_market_common_history(
                crypto=crypto,equities=equity,
                independently_verified_stock_core_opens_utc=STOCK_GRID,
                as_of=AS_OF)

    def test_unverified_equity_grid_and_missing_crypto_market_fail_closed(self):
        crypto,equity=datasets()
        with self.assertRaises(ValueError):
            evaluate_predeclared_twelve_market_common_history(
                crypto=crypto,equities=equity,
                independently_verified_stock_core_opens_utc=STOCK_GRID[:-1],
                as_of=AS_OF)
        broken=dict(crypto);broken.pop("AVAX/USD")
        with self.assertRaises(ValueError):
            evaluate_predeclared_twelve_market_common_history(
                crypto=broken,equities=equity,
                independently_verified_stock_core_opens_utc=STOCK_GRID,
                as_of=AS_OF)

    def test_no_forward_masquerading_and_no_extra_stock_afterhours(self):
        crypto,equity=datasets()
        b=list(crypto["BTC/USD"])
        b[-1]=replace(b[-1],prospective=True)
        with self.assertRaises(ValueError):
            evaluate_predeclared_twelve_market_common_history(
                crypto={**crypto,"BTC/USD":tuple(b)},equities=equity,
                independently_verified_stock_core_opens_utc=STOCK_GRID,
                as_of=AS_OF)
        later=list(equity["SPY"])
        later.append(replace(later[-1],
                             start_utc=later[-1].start_utc+HOUR))
        with self.assertRaises(ValueError):
            evaluate_predeclared_twelve_market_common_history(
                crypto=crypto,equities={**equity,"SPY":tuple(later)},
                independently_verified_stock_core_opens_utc=STOCK_GRID,
                as_of=AS_OF)


if __name__=="__main__":
    unittest.main()

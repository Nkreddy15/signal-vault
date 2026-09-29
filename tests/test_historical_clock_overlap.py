"""Pure cross-asset historical-clock safety tests; no market/provider I/O."""
from __future__ import annotations

import unittest
from datetime import datetime,timedelta,timezone

from signal_vault.historical_clock_overlap import historical_clock_compatibility

UTC=timezone.utc
HOUR=timedelta(hours=1)
START_STOCK=datetime(2026,9,14,14,tzinfo=UTC)
EQUITY_CORE=tuple(
    START_STOCK+timedelta(days=day,hours=h)
    for day in (0,1,2,3,4,7,8,9,10,11) for h in range(6)
)


class HistoricalClockCompatibilityTests(unittest.TestCase):
    def test_actual_six_crypto_history_ends_before_10_stock_sessions_begin(self):
        result=historical_clock_compatibility(
            continuous_crypto_start_utc=datetime(2026,7,1,tzinfo=UTC),
            continuous_crypto_end_utc_exclusive=datetime(2026,9,1,tzinfo=UTC),
            independently_verified_stock_core_opens_utc=EQUITY_CORE)
        self.assertEqual(result["stock_verified_core_hour_count"],60)
        self.assertEqual(result["common_source_closed_bar_open_hours"],0)
        self.assertFalse(result["basic_clock_alignment_ready"])
        self.assertEqual(result["reason_code"],"NO_COMMON_HISTORICAL_UTC_HOURS")
        self.assertFalse(result["twelve_asset_backtest_ran"])
        self.assertFalse(result["cross_market_capital_combined"])
        self.assertFalse(result["portfolio_PnL_comparable_across_disjoint_histories"])
        self.assertEqual(result["broker_order_submission"],"DISABLED")

    def test_aligned_research_dates_would_reach_basic_clock_only_not_trading(self):
        result=historical_clock_compatibility(
            continuous_crypto_start_utc=datetime(2026,9,1,tzinfo=UTC),
            continuous_crypto_end_utc_exclusive=datetime(2026,9,26,tzinfo=UTC),
            independently_verified_stock_core_opens_utc=EQUITY_CORE)
        self.assertEqual(result["common_source_closed_bar_open_hours"],60)
        self.assertTrue(result["basic_clock_alignment_ready"])
        self.assertEqual(
            result["reason_code"],
            "BASIC_CLOCK_ALIGNMENT_POSSIBLE_REQUIRES_SEPARATE_MODEL_AUDIT")
        self.assertFalse(result["twelve_asset_backtest_ran"])
        self.assertFalse(result["history_alone_proves_strategy_edge"])
        self.assertEqual(result["broker_order_submission"],"DISABLED")

    def test_partial_coverage_is_rejected_without_faking_or_forward_filling_stocks(self):
        result=historical_clock_compatibility(
            continuous_crypto_start_utc=datetime(2026,9,24,tzinfo=UTC),
            continuous_crypto_end_utc_exclusive=datetime(2026,9,26,tzinfo=UTC),
            independently_verified_stock_core_opens_utc=EQUITY_CORE)
        self.assertEqual(result["common_source_closed_bar_open_hours"],12)
        self.assertEqual(result["reason_code"],"INSUFFICIENT_ALIGNED_STOCK_CORE_HOURS")
        self.assertFalse(result["basic_clock_alignment_ready"])
        self.assertEqual(len(result["common_core_hour_starts_utc"]),12)

    def test_invalid_utc_or_unsorted_duplicate_core_hours_fail_before_analysis(self):
        valid={
            "continuous_crypto_start_utc":datetime(2026,9,1,tzinfo=UTC),
            "continuous_crypto_end_utc_exclusive":datetime(2026,9,26,tzinfo=UTC),
            "independently_verified_stock_core_opens_utc":EQUITY_CORE,
        }
        cases=(
            {"continuous_crypto_start_utc":datetime(2026,9,1)},
            {"continuous_crypto_end_utc_exclusive":
                datetime(2026,9,1,tzinfo=UTC)},
            {"independently_verified_stock_core_opens_utc":
                (EQUITY_CORE[1],EQUITY_CORE[0])},
            {"independently_verified_stock_core_opens_utc":
                (EQUITY_CORE[0],EQUITY_CORE[0])},
            {"independently_verified_stock_core_opens_utc":
                (EQUITY_CORE[0]+timedelta(minutes=30),)},
            {"minimum_shared_core_hours":0},
        )
        for changes in cases:
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                historical_clock_compatibility(**{**valid,**changes})


if __name__=="__main__":
    unittest.main()

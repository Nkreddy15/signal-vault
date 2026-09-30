"""Cross-market risk governor tests; pure/no broker imports."""
from __future__ import annotations

import unittest
from decimal import Decimal

from signal_vault.cross_market_risk import assess_new_risk

ZERO={
    "crypto":Decimal("0"),
    "us_equity":Decimal("0"),
    "kalshi_event_contract":Decimal("0"),
}

class CrossMarketRiskTests(unittest.TestCase):
    def assess(self,**changes):
        args={
            "lane":"crypto",
            "proposed_max_loss_usd":Decimal("5"),
            "exposure_by_lane":ZERO,
            "open_positions":0,
            "marked_equity_usd":Decimal("100"),
            "daily_anchor_equity_usd":Decimal("100"),
            "peak_equity_usd":Decimal("100"),
            "operator_halted":False,
        }
        args.update(changes)
        return assess_new_risk(**args)

    def test_each_market_lane_can_be_assessed_but_never_authorizes_order(self):
        for lane in ZERO:
            with self.subTest(lane=lane):
                result=self.assess(lane=lane)
                self.assertTrue(result["risk_admissible"])
                self.assertTrue(result["assessment_is_not_trading_authorization"])
                self.assertEqual(result["automatic_order_submission"],"DISABLED")
                self.assertEqual(result["paper_order_submission"],"DISABLED")
                self.assertEqual(result["live_order_submission"],"UNAVAILABLE")

    def test_combined_crypto_stock_kalshi_exposure_shares_one_cap(self):
        result=self.assess(
            lane="kalshi_event_contract",
            proposed_max_loss_usd=Decimal("6"),
            exposure_by_lane={
                "crypto":Decimal("15"),
                "us_equity":Decimal("10"),
                "kalshi_event_contract":Decimal("0"),
            })
        self.assertFalse(result["risk_admissible"])
        self.assertIn("TOTAL_EXPOSURE_CAP",result["rejection_reasons"])

    def test_lane_cap_daily_loss_peak_drawdown_and_operator_halt_fail_closed(self):
        lane=self.assess(
            lane="kalshi_event_contract",
            proposed_max_loss_usd=Decimal("5"),
            exposure_by_lane={**ZERO,"kalshi_event_contract":Decimal("7")})
        self.assertIn("MARKET_LANE_EXPOSURE_CAP",lane["rejection_reasons"])
        daily=self.assess(marked_equity_usd=Decimal("96"))
        self.assertIn("DAILY_LOSS_HALT",daily["rejection_reasons"])
        peak=self.assess(marked_equity_usd=Decimal("89"))
        self.assertIn("PERSISTENT_PEAK_DRAWDOWN_HALT",peak["rejection_reasons"])
        halt=self.assess(operator_halted=True)
        self.assertIn("OPERATOR_HALTED",halt["rejection_reasons"])

    def test_bad_unknown_or_non_decimal_risk_is_rejected(self):
        with self.assertRaises(ValueError):
            self.assess(lane="unknown")
        with self.assertRaises(ValueError):
            self.assess(proposed_max_loss_usd=5)
        with self.assertRaises(ValueError):
            self.assess(exposure_by_lane={**ZERO,"other":Decimal("1")})

if __name__=="__main__":
    unittest.main()

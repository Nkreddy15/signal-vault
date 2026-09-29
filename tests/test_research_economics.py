"""Cost audit matches simulator fill economics; strictly offline."""
import unittest
from decimal import Decimal as D

from signal_vault.backtest import CostAssumptions
from signal_vault.research_economics import (
    break_even_price_move_bps, hypothetical_round_trip, report,
)


class SmallNotionalEconomicsTests(unittest.TestCase):
    def test_zero_cost_break_even_is_zero_and_flat_move_is_flat(self):
        free = CostAssumptions(taker_fee_rate=D("0"), slippage_rate=D("0"))
        self.assertEqual(break_even_price_move_bps(costs=free), 0)
        out = hypothetical_round_trip(price_move_bps=D("0"), costs=free)
        self.assertEqual(D(out["modeled_round_trip_pnl_usd"]), 0)

    def test_breakeven_is_strictly_positive_and_matches_exact_fill_equations(self):
        cfg = CostAssumptions()
        bps = break_even_price_move_bps(costs=cfg)
        self.assertGreater(bps, D("70"))
        self.assertLess(bps, D("72"))
        at_break_even = hypothetical_round_trip(price_move_bps=bps, costs=cfg)
        self.assertLess(abs(D(at_break_even["modeled_round_trip_pnl_usd"])), D("1e-20"))
        below = hypothetical_round_trip(price_move_bps=bps-D("1"), costs=cfg)
        above = hypothetical_round_trip(price_move_bps=bps+D("1"), costs=cfg)
        self.assertLess(D(below["modeled_round_trip_pnl_usd"]), 0)
        self.assertGreater(D(above["modeled_round_trip_pnl_usd"]), 0)

    def test_flat_price_loses_when_costs_exist(self):
        out = hypothetical_round_trip(price_move_bps=D("0"))
        self.assertEqual(out["buy_budget_usd"], "15.00")
        self.assertEqual(D(out["modeled_buy_fee_usd"]), D("0.0375"))
        self.assertLess(D(out["modeled_round_trip_pnl_usd"]), D("-0.10"))

    def test_invalid_price_changes_fail(self):
        for invalid in (D("NaN"), D("Infinity"), D("-10000"), D("-10001"), 0.5, "25"):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                hypothetical_round_trip(price_move_bps=invalid)

    def test_report_is_explicitly_non_executable(self):
        result = report()
        self.assertEqual(result["broker_order_submission"], "DISABLED")
        self.assertEqual(result["kind"], "OFFLINE_HYPOTHETICAL_SMALL_NOTIONAL_COST_AUDIT")
        self.assertEqual(len(result["scenarios"]), 8)


if __name__ == "__main__":
    unittest.main()

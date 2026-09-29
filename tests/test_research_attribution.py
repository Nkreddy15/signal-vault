"""Regression tests for descriptive trade attribution; no broker/data API use."""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

from signal_vault.backtest import SimulatedFill, simulate
from signal_vault.market_data import Bar
from signal_vault.research_attribution import attribute_trades
from signal_vault.research_v02 import V01, V02


START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def synthetic():
    values = [100] * 20 + [90] * 12 + [120] * 12 + [80] * 12
    return [Bar(START + timedelta(hours=i), D(v), D(v + 1), D(v - 1),
                D(v), D("10"), "attribution-test") for i, v in enumerate(values)]


def sample_result():
    rows = synthetic()
    return simulate(rows, as_of=rows[-1].close_time, strategy=V01)


def fill(side, hours, qty, cash_delta):
    t = (START + timedelta(hours=hours)).isoformat()
    return SimulatedFill(t, side, D("100"), D("100"), D(qty),
                         D(cash_delta), D("0.01"), f"diagnostic-{hours}")


class TradeAttributionTests(unittest.TestCase):
    def test_both_strategy_results_reconcile(self):
        rows = synthetic()
        for strategy in (V01, V02):
            with self.subTest(strategy=strategy.strategy_version):
                result = simulate(rows, as_of=rows[-1].close_time, strategy=strategy)
                out = attribute_trades(result)
                self.assertEqual(out["reconciliation"], "PASSED")
                self.assertEqual(out["full_sample_net_pnl_usd"], str(result.net_pnl_usd))
                self.assertEqual(out["open_position"], result.marked_open_base_qty > 0)
                buckets = ("held_at_most_6_hours", "held_over_6_under_24_hours",
                           "held_at_least_24_hours")
                self.assertEqual(sum(out[k]["completed_trades"] for k in buckets),
                                 out["completed"]["completed_trades"])
                self.assertEqual(
                    sum(D(out[k]["combined_net_pnl_usd"]) for k in buckets),
                    D(out["completed"]["combined_net_pnl_usd"])
                )

    def test_nonoverlapping_trade_duration_buckets_and_open_mark(self):
        raw = (
            fill("buy", 0, "0.1", "-15"), fill("sell", 3, "0.1", "16"),
            fill("buy", 4, "0.1", "-15"), fill("sell", 14, "0.1", "13"),
            fill("buy", 15, "0.1", "-15"), fill("sell", 41, "0.1", "15.5"),
            fill("buy", 42, "0.1", "-15"),
        )
        result = replace(sample_result(), fills=raw, last_mark_price=D("100"),
                         net_pnl_usd=D("-5.5"))
        out = attribute_trades(result)
        self.assertEqual(out["completed"]["completed_trades"], 3)
        self.assertEqual(out["completed"]["profitable"], 2)
        self.assertEqual(out["completed"]["losing"], 1)
        self.assertEqual(D(out["median_holding_hours"]), D("10"))
        self.assertEqual(out["held_at_most_6_hours"]["completed_trades"], 1)
        self.assertEqual(out["held_over_6_under_24_hours"]["completed_trades"], 1)
        self.assertEqual(out["held_at_least_24_hours"]["completed_trades"], 1)
        self.assertEqual(out["completed"]["combined_net_pnl_usd"], "-0.5")
        self.assertEqual(out["open_position_marked_pnl_usd"], "-5.0")
        self.assertEqual(out["reconciliation"], "PASSED")

    def test_inconsistent_fills_fail_closed(self):
        base = sample_result()
        for bad in (
            (fill("sell", 0, "0.1", "10"),),
            (fill("buy", 0, "0.1", "-15"), fill("buy", 1, "0.1", "-15")),
            (fill("buy", 0, "0.1", "-15"), fill("sell", 1, "0.2", "10")),
            (fill("buy", 0, "0.1", "-15"), fill("sell", 0, "0.1", "10")),
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                attribute_trades(replace(base, fills=bad))
        with self.assertRaisesRegex(ValueError, "does not reconcile"):
            attribute_trades(replace(base, fills=(), net_pnl_usd=D("2")))


if __name__ == "__main__":
    unittest.main()

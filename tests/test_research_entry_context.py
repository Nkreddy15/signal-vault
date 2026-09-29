"""No-future-data and accounting regression tests for entry-context diagnostics."""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

from signal_vault.backtest import simulate
from signal_vault.market_data import Bar
from signal_vault.research_entry_context import entry_features, compare_entry_context
from signal_vault.research_v02 import V01, V02
from signal_vault.strategy import Action, generate_signal

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def candles():
    seq = [100] * 20 + [90] * 12 + [120] * 12 + [80] * 12 + [120] * 12
    return [Bar(START + timedelta(hours=i), D(v), D(v + 1), D(v - 1),
                D(v), D("10"), "entry-context-test") for i, v in enumerate(seq)]


class EntryContextTests(unittest.TestCase):
    def test_closed_bar_features_cannot_use_execution_or_later_candle(self):
        bars = candles()
        for cfg in (V01, V02):
            with self.subTest(cfg=cfg.strategy_version):
                idx = next(i for i in range(cfg.slow_hours + 2, len(bars))
                           if generate_signal(bars[:i], cfg).action is Action.BUY)
                features = entry_features(bars, idx, cfg)
                self.assertEqual(set(features), {
                    "ema_spread_bps", "prior_6h_close_return_bps",
                    "prior_24h_close_return_bps", "prior_24h_high_low_range_bps",
                    "prior_24h_signed_trend_efficiency",
                })
                changed = list(bars)
                for i in range(idx, len(changed)):
                    changed[i] = replace(changed[i], open=D("600"), high=D("601"),
                                         low=D("599"), close=D("600"))
                self.assertEqual(features, entry_features(changed, idx, cfg))
                self.assertGreater(features["ema_spread_bps"], D("0"))

    def test_wrong_signal_entry_index_and_strategy_version_fail(self):
        bars = candles()
        hold_idx = next(i for i in range(V01.slow_hours + 2, len(bars))
                        if generate_signal(bars[:i], V01).action is Action.HOLD)
        with self.assertRaisesRegex(ValueError, "real version-matched BUY"):
            entry_features(bars, hold_idx, V01)
        with self.assertRaisesRegex(ValueError, "insufficient"):
            entry_features(bars, 10, V01)
        baseline = simulate(bars, as_of=bars[-1].close_time, strategy=V01)
        with self.assertRaisesRegex(ValueError, "strategy version mismatch"):
            compare_entry_context(bars, baseline, V02)

    def test_completed_and_open_trade_counts_reconcile(self):
        bars = candles()
        for cfg in (V01, V02):
            with self.subTest(cfg=cfg.strategy_version):
                simulated = simulate(bars, as_of=bars[-1].close_time, strategy=cfg)
                result = compare_entry_context(bars, simulated, cfg)
                self.assertEqual(result["reconciliation"], "PASSED")
                self.assertEqual(
                    result["observed_winning_trades"]["trade_count"]
                    + result["observed_losing_trades"]["trade_count"],
                    result["total_completed"]["trade_count"])
                self.assertEqual(
                    result["observed_exit_under_24_hours"]["trade_count"]
                    + result["observed_exit_at_least_24_hours"]["trade_count"],
                    result["total_completed"]["trade_count"])

    def test_bad_evidence_is_not_silently_attributed(self):
        bars = candles()
        result = simulate(bars, as_of=bars[-1].close_time, strategy=V01)
        self.assertTrue(result.fills)
        altered = list(result.fills)
        altered[0] = replace(altered[0], evidence_id="forged")
        with self.assertRaisesRegex(ValueError, "evidence does not match"):
            compare_entry_context(bars, replace(result, fills=tuple(altered)), V01)


if __name__ == "__main__":
    unittest.main()

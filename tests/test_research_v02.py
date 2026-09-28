"""Isolated v0.2 research hypothesis. Default v0.1 and sell timing must not change."""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.market_data import Bar
from signal_vault.strategy import Action, StrategyConfig, generate_signal
from signal_vault.backtest import simulate
from signal_vault.research_v02 import V01, V02


START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def synthetic():
    prices = [100] * 8 + [90] * 8 + [120] * 8 + [80] * 12
    return [
        Bar(START + timedelta(hours=i), Decimal(px), Decimal(px + 1),
            Decimal(px - 1), Decimal(px), Decimal(10), "v02-synthetic")
        for i, px in enumerate(prices)
    ]


class ResearchV02Tests(unittest.TestCase):
    def test_default_config_is_unchanged_and_variant_requires_new_version(self):
        self.assertEqual(StrategyConfig(), V01)
        self.assertEqual(V01.entry_confirmation_bars, 1)
        self.assertEqual(V02.entry_confirmation_bars, 2)
        with self.assertRaisesRegex(ValueError, "own strategy version"):
            StrategyConfig(entry_confirmation_bars=2)
        for val in (0, 3, True, 1.5):
            with self.subTest(val=val), self.assertRaises(ValueError):
                StrategyConfig(strategy_version="invalid-candidate", entry_confirmation_bars=val)

    def test_buy_requires_two_successive_closed_positive_ema_states(self):
        seq = synthetic()
        old = [(i, generate_signal(seq[:i], V01).action)
               for i in range(V01.slow_hours + 2, len(seq) + 1)]
        new = [(i, generate_signal(seq[:i], V02).action)
               for i in range(V02.slow_hours + 2, len(seq) + 1)]
        old_buys = [i for i, side in old if side is Action.BUY]
        new_buys = [i for i, side in new if side is Action.BUY]
        self.assertTrue(old_buys)
        self.assertEqual(new_buys, [i + 1 for i in old_buys])
        self.assertEqual(len(set(new_buys)), len(new_buys))
        self.assertEqual([i for i, side in old if side is Action.SELL],
                         [i for i, side in new if side is Action.SELL])

    def test_future_bar_cannot_rewrite_candidate_signal(self):
        seq = synthetic()
        amended = list(seq)
        amended[-1] = replace(amended[-1], close=Decimal(800), high=Decimal(801))
        for i in range(V02.slow_hours + 2, len(seq)):
            self.assertEqual(generate_signal(seq[:i], V02), generate_signal(amended[:i], V02))

    def test_backtest_is_offline_and_uses_versioned_candidate(self):
        seq = synthetic()
        baseline = simulate(seq, as_of=seq[-1].close_time)
        variant = simulate(seq, as_of=seq[-1].close_time, strategy=V02)
        self.assertEqual(baseline.strategy_version, V01.strategy_version)
        self.assertEqual(variant.strategy_version, V02.strategy_version)
        self.assertEqual(variant.to_dict()["kind"], "OFFLINE_HYPOTHETICAL_RESEARCH_NOT_PROVIDER_PAPER")


if __name__ == "__main__":
    unittest.main()

"""v0.3 preregistered prior-day momentum hypothesis safety tests."""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

from signal_vault.backtest import CostAssumptions, simulate
from signal_vault.market_data import Bar
from signal_vault.research_v02 import V01, V02
from signal_vault.research_v03 import V03, development_gate
from signal_vault.strategy import Action, StrategyConfig, generate_signal

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def candles(values):
    return [
        Bar(START + timedelta(hours=i), D(str(px)), D(str(px)) + D("1"),
            D(str(px)) - D("1"), D(str(px)), D("10"), "v03-synthetic")
        for i, px in enumerate(values)
    ]


def index_of_first_buy(bars, config):
    return next(i for i in range(config.slow_hours + 2, len(bars))
                if generate_signal(bars[:i], config).action is Action.BUY)


class ResearchV03Tests(unittest.TestCase):
    def test_config_is_opt_in_versioned_finite_and_not_combinable(self):
        self.assertIsNone(V01.entry_minimum_prior_24h_return_bps)
        self.assertIsNone(V02.entry_minimum_prior_24h_return_bps)
        self.assertEqual(V03.entry_minimum_prior_24h_return_bps, D("50"))
        self.assertEqual(V03.entry_confirmation_bars, 1)
        with self.assertRaisesRegex(ValueError, "own candidate version"):
            StrategyConfig(entry_minimum_prior_24h_return_bps=D("50"))
        with self.assertRaisesRegex(ValueError, "cannot combine"):
            StrategyConfig(strategy_version="combined-research", entry_confirmation_bars=2,
                           entry_minimum_prior_24h_return_bps=D("50"))
        for val in ("50", 50, D("NaN"), D("Infinity"), D("-1"), D("10001")):
            with self.subTest(val=val), self.assertRaises(ValueError):
                StrategyConfig(strategy_version="v03-invalid", entry_minimum_prior_24h_return_bps=val)

    def test_rejects_weak_completed_prior_day_but_preserves_baseline_buy(self):
        bars = candles([100] * 30 + [D("99.8")] * 20 + [100] * 30)
        i = index_of_first_buy(bars, V01)
        observed_bps = (bars[i-1].close / bars[i-25].close - 1) * D("10000")
        self.assertLess(observed_bps, D("50"))
        self.assertEqual(generate_signal(bars[:i], V01).action, Action.BUY)
        decision = generate_signal(bars[:i], V03)
        self.assertEqual(decision.action, Action.HOLD)
        self.assertIn("vetoed", decision.explanation)

    def test_accepts_strong_completed_prior_day_without_delaying_baseline(self):
        bars = candles([100] * 30 + [90] * 20 + [120] * 30 + [70] * 35)
        i = index_of_first_buy(bars, V01)
        observed_bps = (bars[i-1].close / bars[i-25].close - 1) * D("10000")
        self.assertGreaterEqual(observed_bps, D("50"))
        self.assertEqual(generate_signal(bars[:i], V03).action, Action.BUY)
        # Future execution candle and later bars must not affect the signal.
        changed = list(bars)
        for j in range(i, len(changed)):
            changed[j] = replace(changed[j], open=D("600"), high=D("601"),
                                 low=D("599"), close=D("600"))
        self.assertEqual(generate_signal(bars[:i], V03),
                         generate_signal(changed[:i], V03))
        # A bearish crossover continues to produce the exact same SELL timing.
        baseline_sells = [j for j in range(V01.slow_hours + 2, len(bars) + 1)
                          if generate_signal(bars[:j], V01).action is Action.SELL]
        candidate_sells = [j for j in range(V03.slow_hours + 2, len(bars) + 1)
                           if generate_signal(bars[:j], V03).action is Action.SELL]
        self.assertTrue(baseline_sells)
        self.assertEqual(candidate_sells, baseline_sells)

    def test_baseline_unchanged_and_backtest_research_only(self):
        bars = candles([100] * 30 + [90] * 20 + [120] * 30 + [70] * 35)
        baseline = simulate(bars, as_of=bars[-1].close_time)
        explicit = simulate(bars, as_of=bars[-1].close_time, strategy=V01)
        candidate = simulate(bars, as_of=bars[-1].close_time, strategy=V03)
        self.assertEqual(baseline, explicit)
        self.assertEqual(candidate.strategy_version, V03.strategy_version)
        self.assertEqual(candidate.to_dict()["kind"],
                         "OFFLINE_HYPOTHETICAL_RESEARCH_NOT_PROVIDER_PAPER")

    def test_fixed_gate_rejects_bad_or_inconsistent_evidence(self):
        bars = candles([100] * 30 + [90] * 20 + [120] * 30 + [70] * 35)
        baseline = simulate(bars, as_of=bars[-1].close_time, strategy=V01)
        candidate = simulate(bars, as_of=bars[-1].close_time, strategy=V03)
        free_costs = CostAssumptions(taker_fee_rate=D("0"), slippage_rate=D("0"))
        zero = simulate(bars, as_of=bars[-1].close_time, strategy=V03, costs=free_costs)
        self.assertEqual(development_gate(candidate, baseline, zero)["broker_order_submission"],
                         "DISABLED")
        bad = replace(zero, net_pnl_usd=D("-1"))
        self.assertIn("zero-cost aggregate development P&L is not positive",
                      development_gate(candidate, baseline, bad)["reasons"])
        with self.assertRaisesRegex(ValueError, "different cost assumptions"):
            development_gate(zero, baseline, zero)
        with self.assertRaisesRegex(ValueError, "matching zero-cost"):
            development_gate(candidate, baseline, candidate)


if __name__ == "__main__":
    unittest.main()

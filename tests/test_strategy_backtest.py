import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.backtest import CostAssumptions, simulate
from signal_vault.market_data import Bar
from signal_vault.strategy import StrategyConfig, Action, generate_signal

START = datetime(2026, 8, 1, tzinfo=timezone.utc)


def candles(prices):
    result = []
    for idx, value in enumerate(prices):
        v = Decimal(str(value))
        result.append(Bar(START + timedelta(hours=idx), v, v + Decimal("1"),
                          v - Decimal("1"), v, Decimal("3"), "synthetic-test"))
    return result


class StrategyBacktestTests(unittest.TestCase):
    def test_warmup_returns_hold(self):
        s = generate_signal(candles([100, 100, 101]), StrategyConfig(3, 5))
        self.assertEqual(s.action, Action.HOLD)

    def test_deterministic_cross_detected_only_after_close(self):
        seq = candles([100] * 8 + [90] * 8 + [120] * 8)
        cfg = StrategyConfig(3, 5)
        signals = [generate_signal(seq[:i], cfg) for i in range(7, len(seq) + 1)]
        self.assertIn(Action.BUY, [s.action for s in signals])
        self.assertEqual(signals[-1], generate_signal(seq, cfg))
        self.assertEqual(len({s.evidence_id for s in signals}), len(signals))

    def test_no_signal_uses_future_bar(self):
        seq = candles([100] * 8 + [90] * 8 + [120] * 8 + [80] * 10)
        cfg = StrategyConfig(3, 5)
        future_changed = list(seq)
        future_changed[-1] = replace(future_changed[-1], close=Decimal("700"), high=Decimal("701"))
        self.assertEqual(generate_signal(seq[:-1], cfg), generate_signal(future_changed[:-1], cfg))

    def test_bad_costs_are_rejected(self):
        for val in (Decimal("NaN"), Decimal("-1"), Decimal("1.5")):
            with self.subTest(val=val), self.assertRaises(ValueError):
                CostAssumptions(taker_fee_rate=val)
        with self.assertRaises(ValueError):
            CostAssumptions(buy_budget_usd=Decimal("5"))

    def test_backtest_fills_next_open_and_accounts_for_costs(self):
        seq = candles([100] * 8 + [90] * 8 + [120] * 8 + [80] * 10)
        cfg = StrategyConfig(3, 5)
        as_of = seq[-1].close_time
        result = simulate(seq, as_of=as_of, strategy=cfg)
        self.assertGreaterEqual(len(result.fills), 1)
        self.assertTrue(all(f.estimated_fee_usd > 0 for f in result.fills))
        self.assertEqual(result.net_pnl_usd, result.final_equity_usd - Decimal("100"))
        self.assertEqual(result.to_dict()["kind"], "OFFLINE_HYPOTHETICAL_RESEARCH_NOT_PROVIDER_PAPER")
        signal = None
        for i in range(cfg.slow_hours + 2, len(seq)):
            maybe = generate_signal(seq[:i], cfg)
            if maybe.evidence_id == result.fills[0].evidence_id:
                signal = (maybe, i)
                break
        self.assertIsNotNone(signal)
        self.assertEqual(result.fills[0].time, seq[signal[1]].start.isoformat())
        self.assertEqual(result.fills[0].reference_price, seq[signal[1]].open)

    def test_costs_reduce_simulated_equity(self):
        seq = candles([100] * 8 + [90] * 8 + [120] * 8 + [80] * 10)
        cfg = StrategyConfig(3, 5)
        costly = simulate(seq, as_of=seq[-1].close_time, strategy=cfg)
        free = simulate(seq, as_of=seq[-1].close_time, strategy=cfg,
                        costs=CostAssumptions(taker_fee_rate=Decimal("0"), slippage_rate=Decimal("0")))
        self.assertLessEqual(costly.final_equity_usd, free.final_equity_usd)

    def test_open_bar_rejected(self):
        seq = candles([100] * 40)
        with self.assertRaisesRegex(ValueError, "open / future"):
            simulate(seq, as_of=seq[-1].start + timedelta(minutes=1),
                     strategy=StrategyConfig(3, 5))


if __name__ == "__main__":
    unittest.main()

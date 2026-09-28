import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.backtest import chronological_research_folds
from signal_vault.market_data import Bar
from signal_vault.strategy import StrategyConfig

START = datetime(2026, 8, 1, tzinfo=timezone.utc)


def sample(n=120):
    bars = []
    for i in range(n):
        px = Decimal(100 + (i // 8 % 4) * 5 - (i // 16 % 3) * 8)
        bars.append(Bar(START + timedelta(hours=i), px, px + 1, px - 1, px,
                        Decimal(12), "test-synthetic"))
    return bars


class ChronologicalResearchTests(unittest.TestCase):
    def test_disjoint_evaluation_windows_have_past_only_warmup(self):
        data = sample()
        cfg = StrategyConfig(3, 5)
        folds = chronological_research_folds(data, as_of=data[-1].close_time,
                                             strategy=cfg, evaluation_hours=20)
        self.assertGreater(len(folds), 2)
        self.assertEqual(folds[0].evaluation_start, data[7].start.isoformat())
        for old, new in zip(folds, folds[1:]):
            self.assertEqual(old.evaluation_end, new.evaluation_start)
            self.assertEqual(new.warmup_hours, 7)
        self.assertEqual(folds[-1].evaluation_end, data[-1].close_time.isoformat())

    def test_future_fold_values_cannot_change_prior_fold(self):
        data = sample()
        cfg = StrategyConfig(3, 5)
        before = chronological_research_folds(data, as_of=data[-1].close_time,
                                               strategy=cfg, evaluation_hours=20)
        changed = list(data)
        changed[-1] = replace(changed[-1], close=Decimal(500), high=Decimal(501))
        after = chronological_research_folds(changed, as_of=changed[-1].close_time,
                                              strategy=cfg, evaluation_hours=20)
        self.assertEqual(before[0], after[0])
        self.assertEqual(before[1], after[1])

    def test_requires_full_initial_fold(self):
        data = sample(20)
        with self.assertRaisesRegex(ValueError, "not enough"):
            chronological_research_folds(data, as_of=data[-1].close_time,
                                         strategy=StrategyConfig(3, 5), evaluation_hours=20)


if __name__ == "__main__":
    unittest.main()

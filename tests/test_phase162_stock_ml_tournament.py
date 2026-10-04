from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.ci_historical_equities import SYMBOLS
from signal_vault.research_universe import ResearchBar
from signal_vault.stock_ml_tournament import (
    COST_SCENARIOS,
    FEATURES,
    HORIZONS,
    _bounds,
    _build_rows,
    _split,
)


def _synthetic():
    # Use a deterministic irregular market clock: six bars on ordinary days,
    # three bars on every 7th synthetic session. Features must use the actual
    # timestamps rather than a fabricated continuous 24/7 sequence.
    start = datetime(2025, 1, 2, 15, 0, tzinfo=timezone.utc)
    timeline = []
    day = 0
    while len(timeline) < 360:
        bars_this_day = 3 if day % 7 == 6 else 6
        base = start + timedelta(days=day)
        for hour in range(bars_this_day):
            timeline.append(base + timedelta(hours=hour))
            if len(timeline) >= 360:
                break
        day += 1

    datasets = {}
    for sidx, symbol in enumerate(SYMBOLS):
        rows = []
        for i, at in enumerate(timeline):
            close = Decimal("100") + Decimal(sidx * 5) + Decimal(i) * Decimal("0.02")
            rows.append(
                ResearchBar(
                    symbol=symbol,
                    start_utc=at,
                    open=close - Decimal("0.01"),
                    high=close + Decimal("0.04"),
                    low=close - Decimal("0.04"),
                    close=close,
                    volume=Decimal("1000") + Decimal((i + sidx) % 29),
                    feed="alpaca_equity_iex|adjustment=all",
                    captured_utc=timeline[-1] + timedelta(days=2),
                    prospective=False,
                )
            )
        datasets[symbol] = tuple(rows)
    return datasets, tuple(timeline)


class Phase162StockMlTournamentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.datasets, cls.timeline = _synthetic()
        cls.rows, cls.frames = _build_rows(cls.datasets, cls.timeline)

    def test_equity_cost_scenarios_match_declared_round_trip_formula(self):
        self.assertEqual(COST_SCENARIOS["illustrative_low_equity_friction"], 5.0)
        self.assertEqual(COST_SCENARIOS["illustrative_base_equity_friction"], 13.0)
        self.assertEqual(COST_SCENARIOS["illustrative_high_equity_friction"], 38.0)

    def test_irregular_market_clock_still_builds_features(self):
        self.assertEqual(len(self.frames), len(SYMBOLS))
        self.assertTrue(set(FEATURES).issubset(self.rows.columns))
        # The synthetic early-close cadence means bar 44 and 45 are not
        # guaranteed to share a simple modulo-six clock position.
        frame = self.frames[SYMBOLS[0]]
        self.assertIn("session_bucket_sin", frame.columns)
        self.assertIn("session_bucket_cos", frame.columns)

    def test_purged_target_boundaries(self):
        n = len(self.timeline)
        for horizon in HORIZONS:
            train, validation, test, train_cut, validation_cut = _split(
                self.rows,
                n=n,
                horizon=horizon,
            )
            self.assertLess(int(train.time_index.max()) + horizon, train_cut)
            self.assertGreaterEqual(int(validation.time_index.min()), train_cut)
            self.assertLess(
                int(validation.time_index.max()) + horizon,
                validation_cut,
            )
            self.assertGreaterEqual(int(test.time_index.min()), validation_cut)

    def test_fold_bounds_require_meaningful_history(self):
        with self.assertRaises(ValueError):
            _bounds(100, 24)
        train_cut, validation_cut = _bounds(360, 24)
        self.assertGreater(validation_cut, train_cut)
        self.assertLess(validation_cut, 360)


if __name__ == "__main__":
    unittest.main()

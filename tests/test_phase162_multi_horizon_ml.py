from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.multi_horizon_ml_tournament import (
    FEATURES,
    HISTORICAL_HOURS,
    HORIZONS,
    TRAIN_CUT,
    VALIDATION_CUT,
    _build_rows,
    _split,
)
from signal_vault.relative_strength_tilt_research import SYMBOLS
from signal_vault.research_universe import ResearchBar


def _datasets():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    out = {}
    for sidx, symbol in enumerate(sorted(SYMBOLS)):
        rows = []
        base = Decimal("100") + Decimal(sidx * 9)
        for i in range(HISTORICAL_HOURS):
            drift = Decimal(i) * Decimal("0.015")
            wave = Decimal((i % 23) - 11) * Decimal("0.003")
            close = base + drift + wave
            rows.append(
                ResearchBar(
                    symbol=symbol,
                    start_utc=start + timedelta(hours=i),
                    open=close - Decimal("0.02"),
                    high=close + Decimal("0.05"),
                    low=close - Decimal("0.05"),
                    close=close,
                    volume=Decimal("1000") + Decimal((i + sidx) % 37),
                    feed="alpaca_crypto_us",
                    captured_utc=start + timedelta(hours=HISTORICAL_HOURS + 2),
                    prospective=False,
                )
            )
        out[symbol] = tuple(rows)
    return out


class Phase162MultiHorizonMlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.datasets = _datasets()
        cls.rows, cls.frames = _build_rows(cls.datasets)

    def test_expected_feature_columns_exist(self):
        self.assertTrue(set(FEATURES).issubset(set(self.rows.columns)))
        for horizon in HORIZONS:
            self.assertIn(f"target_{horizon}h", self.rows.columns)

    def test_purged_boundaries_keep_targets_inside_fold(self):
        for horizon in HORIZONS:
            train, validation, holdout = _split(self.rows, horizon)
            self.assertLess(int(train.time_index.max()) + horizon, TRAIN_CUT)
            self.assertGreaterEqual(int(validation.time_index.min()), TRAIN_CUT)
            self.assertLess(
                int(validation.time_index.max()) + horizon,
                VALIDATION_CUT,
            )
            self.assertGreaterEqual(
                int(holdout.time_index.min()),
                VALIDATION_CUT,
            )

    def test_future_mutation_does_not_change_earlier_features(self):
        symbol = sorted(SYMBOLS)[0]
        target_index = 500
        future_index = target_index + 200

        before = self.frames[symbol].loc[target_index, list(FEATURES)].copy()

        mutated = dict(self.datasets)
        rows = list(mutated[symbol])
        old = rows[future_index]
        rows[future_index] = ResearchBar(
            symbol=old.symbol,
            start_utc=old.start_utc,
            open=old.open * Decimal("3"),
            high=old.high * Decimal("3"),
            low=old.low * Decimal("3"),
            close=old.close * Decimal("3"),
            volume=old.volume * Decimal("3"),
            feed=old.feed,
            captured_utc=old.captured_utc,
            prospective=False,
        )
        mutated[symbol] = tuple(rows)

        _, after_frames = _build_rows(mutated)
        after = after_frames[symbol].loc[target_index, list(FEATURES)]
        for name in FEATURES:
            self.assertAlmostEqual(float(before[name]), float(after[name]), places=12)

    def test_target_uses_next_open_and_future_close(self):
        symbol = sorted(SYMBOLS)[0]
        horizon = 48
        index = 600
        frame = self.frames[symbol]
        expected = (
            float(frame.loc[index + horizon, "close"])
            / float(frame.loc[index + 1, "open"])
            - 1.0
        )
        observed = float(
            self.rows[
                (self.rows.symbol == symbol)
                & (self.rows.time_index == index)
            ][f"target_{horizon}h"].iloc[0]
        )
        self.assertAlmostEqual(observed, expected, places=12)


if __name__ == "__main__":
    unittest.main()

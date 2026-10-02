from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.ml_candidate_tournament import (
    FEATURE_NAMES,
    HISTORICAL_HOURS,
    LOOKBACK,
    _safe_return,
    build_observations,
)
from signal_vault.relative_strength_tilt_research import SYMBOLS
from signal_vault.research_universe import ResearchBar


def _datasets():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    out = {}
    for sidx, symbol in enumerate(sorted(SYMBOLS)):
        rows = []
        base = Decimal("100") + Decimal(sidx * 7)
        for i in range(HISTORICAL_HOURS):
            # Smooth deterministic trend + repeating perturbation. No future
            # values are referenced while constructing any earlier row.
            drift = Decimal(i) * Decimal("0.01")
            wave = Decimal((i % 17) - 8) * Decimal("0.002")
            close = base + drift + wave
            rows.append(
                ResearchBar(
                    symbol=symbol,
                    start_utc=start + timedelta(hours=i),
                    open=close - Decimal("0.01"),
                    high=close + Decimal("0.03"),
                    low=close - Decimal("0.03"),
                    close=close,
                    volume=Decimal("1000") + Decimal((i + sidx) % 31),
                    feed="alpaca_crypto_us",
                    captured_utc=start + timedelta(hours=HISTORICAL_HOURS + 1),
                    prospective=False,
                )
            )
        out[symbol] = tuple(rows)
    return out


class Phase162MlCandidateTournamentTests(unittest.TestCase):
    def test_safe_return(self):
        self.assertAlmostEqual(_safe_return(101.0, 100.0), 0.01)
        with self.assertRaises(ValueError):
            _safe_return(1.0, 0.0)

    def test_causal_features_have_expected_shape(self):
        observations = build_observations(_datasets())
        expected_hours = HISTORICAL_HOURS - 1 - LOOKBACK
        self.assertEqual(len(observations), expected_hours * len(SYMBOLS))
        first = observations[0]
        self.assertEqual(len(first.features), len(FEATURE_NAMES))
        self.assertEqual(first.time_index, LOOKBACK)

    def test_future_mutation_does_not_change_earlier_features(self):
        data = _datasets()
        before = build_observations(data)
        target_index = LOOKBACK + 10
        original = next(
            row for row in before
            if row.symbol == sorted(SYMBOLS)[0] and row.time_index == target_index
        )

        symbol = sorted(SYMBOLS)[0]
        mutated = dict(data)
        rows = list(mutated[symbol])
        future_index = target_index + 50
        old = rows[future_index]
        rows[future_index] = ResearchBar(
            symbol=old.symbol,
            start_utc=old.start_utc,
            open=old.open * Decimal("5"),
            high=old.high * Decimal("5"),
            low=old.low * Decimal("5"),
            close=old.close * Decimal("5"),
            volume=old.volume * Decimal("5"),
            feed=old.feed,
            captured_utc=old.captured_utc,
            prospective=False,
        )
        mutated[symbol] = tuple(rows)

        after = build_observations(mutated)
        changed = next(
            row for row in after
            if row.symbol == symbol and row.time_index == target_index
        )
        self.assertEqual(original.features, changed.features)
        self.assertEqual(original.next_return, changed.next_return)


if __name__ == "__main__":
    unittest.main()

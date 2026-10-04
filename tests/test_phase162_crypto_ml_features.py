from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import numpy as np

from signal_vault.crypto_ml_features import (
    DEPLOYABLE_CRYPTO_FEATURES,
    MINIMUM_CLOSED_BARS,
    build_crypto_feature_frames,
    latest_crypto_feature_matrix,
)
from signal_vault.research_universe import ResearchBar


SYMBOLS = ("BTC/USD", "ETH/USD", "SOL/USD")
START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def data(count=80):
    result = {}
    for sidx, symbol in enumerate(SYMBOLS):
        rows = []
        for i in range(count):
            close = (
                Decimal("100")
                + Decimal(sidx * 10)
                + Decimal(i) * Decimal("0.08")
                + Decimal((i % 9) - 4) * Decimal("0.01")
            )
            at = START + timedelta(hours=i)
            rows.append(
                ResearchBar(
                    symbol=symbol,
                    start_utc=at,
                    open=close - Decimal("0.02"),
                    high=close + Decimal("0.05"),
                    low=close - Decimal("0.05"),
                    close=close,
                    volume=Decimal("1000") + Decimal((i + sidx) % 20),
                    feed="alpaca_crypto_us",
                    captured_utc=START + timedelta(hours=count + 2),
                    prospective=False,
                )
            )
        result[symbol] = tuple(rows)
    return result


class Phase162CryptoMlFeatureTests(unittest.TestCase):
    def test_requires_73_closes_for_72_return_volatility(self):
        with self.assertRaises(ValueError):
            build_crypto_feature_frames(data(MINIMUM_CLOSED_BARS - 1))
        frames = build_crypto_feature_frames(data(MINIMUM_CLOSED_BARS))
        for frame in frames.values():
            self.assertTrue(
                np.isfinite(
                    frame.iloc[-1][list(DEPLOYABLE_CRYPTO_FEATURES)]
                    .to_numpy(dtype=float)
                ).all()
            )

    def test_latest_matrix_is_aligned_and_deterministic(self):
        symbols, matrix, timestamp = latest_crypto_feature_matrix(data())
        self.assertEqual(symbols, tuple(sorted(SYMBOLS)))
        self.assertEqual(matrix.shape, (len(SYMBOLS), len(DEPLOYABLE_CRYPTO_FEATURES)))
        self.assertEqual(timestamp, (START + timedelta(hours=79)).isoformat())

    def test_future_mutation_cannot_change_earlier_feature_row(self):
        original = data(100)
        frames = build_crypto_feature_frames(original)
        target = 80
        before = frames["BTC/USD"].iloc[target][
            list(DEPLOYABLE_CRYPTO_FEATURES)
        ].to_numpy(dtype=float)

        mutated = dict(original)
        rows = list(mutated["BTC/USD"])
        old = rows[95]
        rows[95] = ResearchBar(
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
        mutated["BTC/USD"] = tuple(rows)
        after_frames = build_crypto_feature_frames(mutated)
        after = after_frames["BTC/USD"].iloc[target][
            list(DEPLOYABLE_CRYPTO_FEATURES)
        ].to_numpy(dtype=float)
        np.testing.assert_allclose(before, after, rtol=0, atol=0)


if __name__ == "__main__":
    unittest.main()

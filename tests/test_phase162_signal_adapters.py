from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.opportunity_engine import Direction, Market
from signal_vault.signal_adapters import (
    directional_model_signal,
    event_probability_model_signal,
)


NOW = datetime(2026, 10, 2, 21, 0, tzinfo=timezone.utc)


class Phase162SignalAdapterTests(unittest.TestCase):
    def test_positive_and_negative_forecasts_map_to_long_and_short(self):
        long_signal = directional_model_signal(
            market=Market.CRYPTO,
            instrument="BTC/USD",
            source_model="rf48",
            strategy_family="ml_return",
            predicted_signed_return=Decimal("0.03"),
            estimated_round_trip_cost_return=Decimal("0.0074"),
            confidence=Decimal("0.70"),
            max_loss_return=Decimal("0.05"),
            generated_utc=NOW,
            valid_until_utc=NOW + timedelta(hours=1),
            horizon_seconds=48 * 3600,
            evidence_id="btc-rf",
            correlation_group="crypto-beta",
            paper_long_supported=True,
        )
        short_signal = directional_model_signal(
            market=Market.US_EQUITY,
            instrument="SPY",
            source_model="hgb24",
            strategy_family="ml_return",
            predicted_signed_return=Decimal("-0.02"),
            estimated_round_trip_cost_return=Decimal("0.0013"),
            confidence=Decimal("0.65"),
            max_loss_return=Decimal("0.04"),
            generated_utc=NOW,
            valid_until_utc=NOW + timedelta(hours=1),
            horizon_seconds=24 * 3600,
            evidence_id="spy-hgb",
            correlation_group="index-beta",
            paper_short_supported=False,
        )
        self.assertEqual(long_signal.direction, Direction.LONG)
        self.assertTrue(long_signal.paper_executable)
        self.assertEqual(short_signal.direction, Direction.SHORT)
        self.assertFalse(short_signal.paper_executable)

    def test_zero_direction_returns_no_signal(self):
        result = directional_model_signal(
            market=Market.CRYPTO,
            instrument="ETH/USD",
            source_model="flat",
            strategy_family="ml_return",
            predicted_signed_return=Decimal("0"),
            estimated_round_trip_cost_return=Decimal("0.0074"),
            confidence=Decimal("0.50"),
            max_loss_return=Decimal("0.05"),
            generated_utc=NOW,
            valid_until_utc=NOW + timedelta(hours=1),
            horizon_seconds=3600,
            evidence_id="flat",
            correlation_group="crypto-beta",
        )
        self.assertIsNone(result)

    def test_event_probability_adapter_selects_yes_and_no_by_expected_value(self):
        yes = event_probability_model_signal(
            ticker="KX-YES",
            source_model="event_model_a",
            strategy_family="event_probability",
            estimated_yes_probability=Decimal("0.72"),
            probability_confidence=Decimal("0.70"),
            yes_ask_probability=Decimal("0.55"),
            no_ask_probability=Decimal("0.47"),
            estimated_round_trip_fee_return=Decimal("0.01"),
            generated_utc=NOW,
            valid_until_utc=NOW + timedelta(minutes=5),
            horizon_seconds=86400,
            evidence_id="event-a",
            correlation_group="macro",
            paper_demo_supported=True,
        )
        no = event_probability_model_signal(
            ticker="KX-NO",
            source_model="event_model_b",
            strategy_family="event_probability",
            estimated_yes_probability=Decimal("0.25"),
            probability_confidence=Decimal("0.75"),
            yes_ask_probability=Decimal("0.40"),
            no_ask_probability=Decimal("0.62"),
            estimated_round_trip_fee_return=Decimal("0.01"),
            generated_utc=NOW,
            valid_until_utc=NOW + timedelta(minutes=5),
            horizon_seconds=86400,
            evidence_id="event-b",
            correlation_group="macro",
        )
        self.assertEqual(yes.direction, Direction.YES)
        self.assertTrue(yes.paper_executable)
        self.assertEqual(no.direction, Direction.NO)
        self.assertFalse(no.paper_executable)

    def test_event_no_edge_returns_none(self):
        result = event_probability_model_signal(
            ticker="KX-NOEDGE",
            source_model="event_model",
            strategy_family="event_probability",
            estimated_yes_probability=Decimal("0.50"),
            probability_confidence=Decimal("0.70"),
            yes_ask_probability=Decimal("0.51"),
            no_ask_probability=Decimal("0.51"),
            estimated_round_trip_fee_return=Decimal("0.01"),
            generated_utc=NOW,
            valid_until_utc=NOW + timedelta(minutes=5),
            horizon_seconds=86400,
            evidence_id="event-flat",
            correlation_group="macro",
            minimum_model_net_edge=Decimal("0.005"),
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

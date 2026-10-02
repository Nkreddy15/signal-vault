from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.ensemble_signals import (
    ModelSignal,
    build_ensemble_opportunities,
)
from signal_vault.opportunity_engine import Direction, Market


NOW = datetime(2026, 10, 2, 20, 0, tzinfo=timezone.utc)


def signal(
    model: str,
    evidence: str,
    *,
    market=Market.CRYPTO,
    instrument="BTC/USD",
    direction=Direction.LONG,
    family="ml",
    gross="0.025",
    cost="0.0074",
    confidence="0.70",
    max_loss="0.05",
    paper=True,
):
    return ModelSignal(
        market=market,
        instrument=instrument,
        source_model=model,
        strategy_family=family,
        direction=direction,
        generated_utc=NOW - timedelta(minutes=1),
        valid_until_utc=NOW + timedelta(hours=2),
        horizon_seconds=24 * 3600,
        expected_gross_return=Decimal(gross),
        estimated_round_trip_cost_return=Decimal(cost),
        confidence=Decimal(confidence),
        max_loss_return=Decimal(max_loss),
        evidence_id=evidence,
        correlation_group="crypto-beta" if market is Market.CRYPTO else "other",
        paper_executable=paper,
    )


class Phase162EnsembleSignalTests(unittest.TestCase):
    def test_two_independent_models_can_create_one_consensus_opportunity(self):
        result = build_ensemble_opportunities(
            (
                signal("random_forest", "rf-1", gross="0.030"),
                signal("hist_gradient", "hgb-1", gross="0.026"),
            ),
            as_of=NOW,
        )
        self.assertEqual(len(result.opportunities), 1)
        item = result.opportunities[0]
        self.assertEqual(item.direction, Direction.LONG)
        self.assertEqual(
            item.component_models,
            ("hist_gradient", "random_forest"),
        )
        self.assertGreater(item.expected_net_return, Decimal("0"))
        self.assertEqual(item.ensemble_consensus, Decimal("1"))

    def test_one_narrow_model_is_not_enough_by_default(self):
        result = build_ensemble_opportunities(
            (signal("ema_only", "ema-1", family="ema"),),
            as_of=NOW,
        )
        self.assertEqual(result.opportunities, ())
        self.assertEqual(
            result.rejected_groups[0]["reason"],
            "INSUFFICIENT_INDEPENDENT_POSITIVE_MODELS",
        )

    def test_conflicting_models_can_block_consensus(self):
        result = build_ensemble_opportunities(
            (
                signal("long_a", "a", direction=Direction.LONG),
                signal("long_b", "b", direction=Direction.LONG),
                signal("short_a", "c", direction=Direction.SHORT),
                signal("short_b", "d", direction=Direction.SHORT),
            ),
            as_of=NOW,
            min_consensus=Decimal("0.60"),
        )
        self.assertEqual(result.opportunities, ())
        self.assertEqual(
            result.rejected_groups[0]["reason"],
            "INSUFFICIENT_DIRECTIONAL_CONSENSUS",
        )

    def test_event_yes_no_uses_same_consensus_contract(self):
        result = build_ensemble_opportunities(
            (
                signal(
                    "event_value",
                    "ev1",
                    market=Market.EVENT_CONTRACT,
                    instrument="KXTEST",
                    direction=Direction.YES,
                    family="event_value",
                    gross="0.05",
                    cost="0.01",
                ),
                signal(
                    "event_calibration",
                    "ev2",
                    market=Market.EVENT_CONTRACT,
                    instrument="KXTEST",
                    direction=Direction.YES,
                    family="event_probability",
                    gross="0.04",
                    cost="0.01",
                ),
            ),
            as_of=NOW,
        )
        self.assertEqual(len(result.opportunities), 1)
        self.assertEqual(result.opportunities[0].direction, Direction.YES)

    def test_expired_signal_does_not_enter_consensus(self):
        expired = ModelSignal(
            market=Market.US_EQUITY,
            instrument="SPY",
            source_model="old",
            strategy_family="ml",
            direction=Direction.LONG,
            generated_utc=NOW - timedelta(hours=3),
            valid_until_utc=NOW - timedelta(hours=1),
            horizon_seconds=3600,
            expected_gross_return=Decimal("0.02"),
            estimated_round_trip_cost_return=Decimal("0.001"),
            confidence=Decimal("0.8"),
            max_loss_return=Decimal("0.05"),
            evidence_id="expired",
            correlation_group="index",
            paper_executable=True,
        )
        result = build_ensemble_opportunities(
            (expired,),
            as_of=NOW,
            min_independent_models=1,
        )
        self.assertEqual(result.opportunities, ())
        self.assertEqual(result.expired_signal_count, 1)

    def test_paper_executable_requires_all_supporting_models_ready(self):
        result = build_ensemble_opportunities(
            (
                signal("ready", "r1", paper=True),
                signal("research_only", "r2", paper=False),
            ),
            as_of=NOW,
        )
        self.assertEqual(len(result.opportunities), 1)
        self.assertFalse(result.opportunities[0].paper_executable)


if __name__ == "__main__":
    unittest.main()

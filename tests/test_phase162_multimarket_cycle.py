from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.multimarket_cycle import (
    PaperRoute,
    build_multimarket_plan,
)
from signal_vault.opportunity_engine import (
    Direction,
    Market,
    Opportunity,
)


NOW = datetime(2026, 10, 2, 21, 0, tzinfo=timezone.utc)


def _op(candidate_id, market, instrument, direction, *, edge, paper=True):
    return Opportunity(
        market=market,
        instrument=instrument,
        candidate_id=candidate_id,
        strategy_family="phase162-test",
        direction=direction,
        generated_utc=NOW - timedelta(minutes=1),
        valid_until_utc=NOW + timedelta(hours=1),
        horizon_seconds=3600,
        expected_gross_return=Decimal(edge) + Decimal("0.002"),
        estimated_round_trip_cost_return=Decimal("0.002"),
        confidence=Decimal("0.70"),
        max_loss_return=Decimal("0.05") if market is not Market.EVENT_CONTRACT else Decimal("1"),
        evidence_id=f"evidence:{candidate_id}",
        correlation_group=f"group:{market.value}:{candidate_id}",
        paper_executable=paper,
    )


class Phase162MultiMarketCycleTests(unittest.TestCase):
    def setUp(self):
        self.routes = (
            PaperRoute(Market.CRYPTO, "crypto-paper-adapter-v1", True),
            PaperRoute(Market.US_EQUITY, "alpaca-equity-paper-v1", True),
            PaperRoute(Market.EVENT_CONTRACT, "kalshi-demo-v1", True),
        )
        self.items = (
            _op("btc", Market.CRYPTO, "BTC/USD", Direction.LONG, edge="0.020"),
            _op("nvda", Market.US_EQUITY, "NVDA", Direction.LONG, edge="0.018"),
            _op(
                "event",
                Market.EVENT_CONTRACT,
                "KALSHI:TEST",
                Direction.YES,
                edge="0.025",
            ),
        )

    def test_one_cycle_can_plan_three_markets_simultaneously(self):
        plan = build_multimarket_plan(
            self.items,
            as_of=NOW,
            routes=self.routes,
            mode="paper",
        )
        self.assertEqual(len(plan.execution_intents), 3)
        self.assertEqual(
            {intent.market for intent in plan.execution_intents},
            {Market.CRYPTO, Market.US_EQUITY, Market.EVENT_CONTRACT},
        )
        self.assertEqual(plan.order_submission, "DISABLED")
        self.assertEqual(plan.live_trading, "UNAVAILABLE")

    def test_intent_ids_are_deterministic_for_same_cycle(self):
        first = build_multimarket_plan(
            self.items,
            as_of=NOW,
            routes=self.routes,
            mode="paper",
        )
        second = build_multimarket_plan(
            self.items,
            as_of=NOW,
            routes=self.routes,
            mode="paper",
        )
        self.assertEqual(
            [x.client_intent_id for x in first.execution_intents],
            [x.client_intent_id for x in second.execution_intents],
        )

    def test_unverified_route_never_becomes_paper_intent(self):
        routes = (
            PaperRoute(Market.CRYPTO, "crypto-paper-adapter-v1", True),
            PaperRoute(Market.US_EQUITY, "alpaca-equity-paper-v1", True),
            PaperRoute(Market.EVENT_CONTRACT, "kalshi-demo-v1", False),
        )
        plan = build_multimarket_plan(
            self.items,
            as_of=NOW,
            routes=routes,
            mode="paper",
        )
        self.assertEqual(len(plan.execution_intents), 2)
        self.assertEqual(plan.unrouteable_selected_candidate_ids, ("event",))

    def test_no_live_mode_exists(self):
        with self.assertRaises(ValueError):
            build_multimarket_plan(
                self.items,
                as_of=NOW,
                routes=self.routes,
                mode="live",
            )


if __name__ == "__main__":
    unittest.main()

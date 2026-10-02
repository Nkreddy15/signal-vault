from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.event_value import event_contract_opportunity
from signal_vault.opportunity_engine import Direction, Market


NOW = datetime(2026, 10, 2, 20, 0, tzinfo=timezone.utc)


class Phase162EventValueTests(unittest.TestCase):
    def test_selects_yes_when_independent_probability_exceeds_market_ask(self):
        opportunity = event_contract_opportunity(
            ticker="TEST-EVENT-YES",
            candidate_id="event-model-1",
            strategy_family="calibrated-event-model",
            estimated_yes_probability=Decimal("0.70"),
            probability_confidence=Decimal("0.65"),
            yes_ask_probability=Decimal("0.55"),
            no_ask_probability=Decimal("0.47"),
            estimated_round_trip_fee_return=Decimal("0.02"),
            generated_utc=NOW,
            valid_until_utc=NOW + timedelta(minutes=5),
            horizon_seconds=86400,
            evidence_id="evidence:test:yes",
        )
        self.assertIsNotNone(opportunity)
        self.assertEqual(opportunity.market, Market.EVENT_CONTRACT)
        self.assertEqual(opportunity.direction, Direction.YES)
        self.assertGreater(opportunity.expected_net_return, Decimal("0"))

    def test_selects_no_when_no_side_has_better_expected_value(self):
        opportunity = event_contract_opportunity(
            ticker="TEST-EVENT-NO",
            candidate_id="event-model-2",
            strategy_family="calibrated-event-model",
            estimated_yes_probability=Decimal("0.30"),
            probability_confidence=Decimal("0.70"),
            yes_ask_probability=Decimal("0.40"),
            no_ask_probability=Decimal("0.62"),
            estimated_round_trip_fee_return=Decimal("0.01"),
            generated_utc=NOW,
            valid_until_utc=NOW + timedelta(minutes=5),
            horizon_seconds=21600,
            evidence_id="evidence:test:no",
        )
        self.assertIsNotNone(opportunity)
        self.assertEqual(opportunity.direction, Direction.NO)

    def test_returns_none_when_market_has_no_after_cost_edge(self):
        opportunity = event_contract_opportunity(
            ticker="TEST-EVENT-NOEDGE",
            candidate_id="event-model-3",
            strategy_family="calibrated-event-model",
            estimated_yes_probability=Decimal("0.51"),
            probability_confidence=Decimal("0.70"),
            yes_ask_probability=Decimal("0.51"),
            no_ask_probability=Decimal("0.51"),
            estimated_round_trip_fee_return=Decimal("0.01"),
            generated_utc=NOW,
            valid_until_utc=NOW + timedelta(minutes=5),
            horizon_seconds=21600,
            evidence_id="evidence:test:none",
        )
        self.assertIsNone(opportunity)

    def test_does_not_mark_event_contract_paper_ready_without_adapter_evidence(self):
        opportunity = event_contract_opportunity(
            ticker="TEST-EVENT-PAPER",
            candidate_id="event-model-4",
            strategy_family="calibrated-event-model",
            estimated_yes_probability=Decimal("0.75"),
            probability_confidence=Decimal("0.80"),
            yes_ask_probability=Decimal("0.55"),
            no_ask_probability=Decimal("0.47"),
            estimated_round_trip_fee_return=Decimal("0.01"),
            generated_utc=NOW,
            valid_until_utc=NOW + timedelta(minutes=5),
            horizon_seconds=21600,
            evidence_id="evidence:test:paper",
        )
        self.assertFalse(opportunity.paper_executable)


if __name__ == "__main__":
    unittest.main()

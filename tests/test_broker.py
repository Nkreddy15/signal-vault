import unittest
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from signal_vault.broker import LocalDryRunBroker
from signal_vault.domain import Side, TradeIntent
from signal_vault.risk import RiskDecision


class DryRunBrokerTests(unittest.TestCase):
    def setUp(self):
        self.broker = LocalDryRunBroker()
        self.order = TradeIntent(
            market="crypto", venue="alpaca", symbol="BTC/USD", side=Side.BUY,
            notional_usd=Decimal("5"), client_order_id="unique-1",
            signal_id="signal-1", quote_timestamp=datetime.now(timezone.utc),
        )

    def test_approved_intent_is_only_recorded_not_filled(self):
        receipt = self.broker.submit(self.order, RiskDecision(True, ()))
        self.assertEqual(receipt.status, "DRY_RUN_RECORDED_NOT_FILLED")
        self.assertIsNone(receipt.broker_order_id)

    def test_risk_denied_intent_never_recorded(self):
        with self.assertRaises(PermissionError):
            self.broker.submit(self.order, RiskDecision(False, ("policy violation",)))

    def test_duplicate_client_idempotency(self):
        approved = RiskDecision(True, ())
        first = self.broker.submit(self.order, approved)
        second = self.broker.submit(self.order, approved)
        self.assertEqual(first, second)

    def test_conflicting_duplicate_is_blocked(self):
        approved = RiskDecision(True, ())
        self.broker.submit(self.order, approved)
        with self.assertRaisesRegex(ValueError, "collision"):
            self.broker.submit(replace(self.order, notional_usd=Decimal("9")), approved)

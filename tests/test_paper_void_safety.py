"""A draft must never release capital while a provider order might be active."""
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from signal_vault.domain import PortfolioSnapshot, Side, TradeIntent
from signal_vault.paper_order_state import BrokerObservation
from signal_vault.paper_store import PersistentPaperOrderStore
from signal_vault.paper_audit import PaperHoldings

AT = datetime(2026, 9, 28, 22, tzinfo=timezone.utc)


def make_intent(identifier):
    return TradeIntent("crypto", "alpaca", "BTC/USD", Side.BUY, Decimal("15"),
                       identifier, "sig-void-safety", AT)


def portfolio():
    return PortfolioSnapshot(Decimal("100"), Decimal("100"), Decimal("100"), Decimal("100"))


class SubmittedDraftVoidTests(unittest.TestCase):
    def test_unsubmitted_draft_can_be_voided(self):
        with PersistentPaperOrderStore(":memory:") as s:
            s.journal.record(make_intent("void-1"), portfolio(), checked_at=AT,
                             reference_price=Decimal("65000"))
            s.journal.void("void-1", reason="operator withdrew proposal", at=AT)
            self.assertEqual(s.journal.total_reserved_usd(), Decimal("0"))

    def test_submitted_draft_cannot_be_voided_in_any_uncertain_stage(self):
        with PersistentPaperOrderStore(":memory:") as s:
            d = s.journal.record(make_intent("void-2"), portfolio(), checked_at=AT,
                                 reference_price=Decimal("65000"))
            s.begin_submission(d, at=AT, baseline=PaperHoldings("paper-test", Decimal("10000"), Decimal("0"), AT))
            for stage in ("pending", "unknown", "terminal"):
                if stage == "unknown":
                    s.mark_unknown(d.client_order_id, at=AT)
                if stage == "terminal":
                    s.observe_provider(BrokerObservation(d.client_order_id, "broker-void", "canceled"), at=AT)
                with self.subTest(stage=stage), self.assertRaises(PermissionError):
                    s.journal.void(d.client_order_id, reason="try to release", at=AT)
                self.assertEqual(s.journal.total_reserved_usd(), Decimal("15"))
            self.assertNotIn("DRAFT_VOIDED", [e["type"] for e in s.journal.recent_events()])


if __name__ == "__main__":
    unittest.main()

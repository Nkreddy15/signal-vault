import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.domain import TradeIntent, Side, PortfolioSnapshot
from signal_vault.paper_audit import PaperHoldings
from signal_vault.paper_store import PersistentPaperOrderStore
from signal_vault.paper_order_state import BrokerObservation

T = datetime(2026, 9, 28, 22, 50, tzinfo=timezone.utc)


def setup_order(store):
    trade = TradeIntent("crypto", "alpaca", "BTC/USD", Side.BUY, Decimal("15"),
                        "halt-check", "test-risk-signal", T)
    portfolio = PortfolioSnapshot(Decimal("100"), Decimal("100"), Decimal("100"), Decimal("100"))
    return store.journal.record(trade, portfolio, checked_at=T,
                                reference_price=Decimal("65000"))


class KillSwitchTests(unittest.TestCase):
    def test_halt_survives_restart_and_prevents_network_order_transition(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "halt.sqlite"
            with PersistentPaperOrderStore(db) as store:
                order = setup_order(store)
                store.set_operator_halt(True, reason="owner pressed stop", at=T)
                self.assertTrue(store.is_operator_halted())
            with PersistentPaperOrderStore(db) as store:
                self.assertTrue(store.is_operator_halted())
                with self.assertRaisesRegex(PermissionError, "HALT"):
                    store.begin_submission(order, at=T,
                        baseline=PaperHoldings("paper-account", Decimal("10000"), Decimal("0"), T))
                self.assertFalse(store.has_unresolved_provider_order())
                store.set_operator_halt(False, reason="owner reviewed incident", at=T)
                self.assertFalse(store.is_operator_halted())
                store.begin_submission(order, at=T,
                    baseline=PaperHoldings("paper-account", Decimal("10000"), Decimal("0"), T))

    def test_cannot_clear_halt_while_order_unknown(self):
        with PersistentPaperOrderStore(":memory:") as store:
            d = setup_order(store)
            store.begin_submission(d, at=T,
                baseline=PaperHoldings("paper-account", Decimal("10000"), Decimal("0"), T))
            store.mark_unknown(d.client_order_id, at=T)
            store.set_operator_halt(True, reason="uncertain broker response", at=T)
            with self.assertRaises(PermissionError):
                store.set_operator_halt(False, reason="unsafe bypass", at=T)
            self.assertTrue(store.is_operator_halted())
            self.assertIn("HALT_ENABLED", [x["type"] for x in store.journal.recent_events()])

    def test_requires_explicit_reason(self):
        with PersistentPaperOrderStore(":memory:") as store:
            with self.assertRaises(ValueError):
                store.set_operator_halt(True, reason="", at=T)

if __name__ == "__main__":
    unittest.main()

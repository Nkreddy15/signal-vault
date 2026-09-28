import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.domain import PortfolioSnapshot, Side, TradeIntent
from signal_vault.paper_store import PersistentPaperOrderStore
from signal_vault.paper_order_state import BrokerObservation, Stage
from signal_vault.alpaca_paper import PaperOrderDraft

NOW = datetime(2026, 9, 28, 21, 0, tzinfo=timezone.utc)


def intent(i):
    return TradeIntent("crypto", "alpaca", "BTC/USD", Side.BUY, Decimal("15"),
                       f"sv-store-{i}", f"signal-{i}", NOW)


def portfolio():
    return PortfolioSnapshot(Decimal("100"), Decimal("100"), Decimal("100"), Decimal("100"))


class PaperStoreTests(unittest.TestCase):
    def test_state_survives_restart_and_duplicate_post_is_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "paper.db"
            with PersistentPaperOrderStore(p) as book:
                draft = book.journal.record(intent(1), portfolio(), checked_at=NOW, reference_price=Decimal("65000"))
                state = book.begin_submission(draft, at=NOW)
                self.assertEqual(state.stage, Stage.SUBMISSION_PENDING)
                self.assertTrue(book.has_unresolved_provider_order())
                with self.assertRaises(ValueError):
                    book.begin_submission(draft, at=NOW)
            with PersistentPaperOrderStore(p) as restarted:
                self.assertEqual(restarted.get("sv-store-1"), state)
                self.assertTrue(restarted.has_unresolved_provider_order())
                self.assertEqual(restarted.journal.total_reserved_usd(), Decimal("15"))

    def test_unknown_timeout_holds_capital_and_prevents_other_submissions(self):
        with PersistentPaperOrderStore(":memory:") as book:
            a = book.journal.record(intent(1), portfolio(), checked_at=NOW, reference_price=Decimal("65000"))
            b = book.journal.record(intent(2), portfolio(), checked_at=NOW, reference_price=Decimal("65000"))
            book.begin_submission(a, at=NOW)
            book.mark_unknown(a.client_order_id, at=NOW)
            with self.assertRaises(PermissionError):
                book.begin_submission(b, at=NOW)
            self.assertEqual(book.journal.total_reserved_usd(), Decimal("30"))
            self.assertEqual(book.get(a.client_order_id).stage, Stage.UNKNOWN_RESULT)

    def test_requires_exact_durable_draft_before_submission(self):
        with PersistentPaperOrderStore(":memory:") as book:
            with self.assertRaises(PermissionError):
                book.begin_submission(PaperOrderDraft("nonexistent", {}), at=NOW)
            original = book.journal.record(intent(1), portfolio(), checked_at=NOW, reference_price=Decimal("65000"))
            with self.assertRaises(PermissionError):
                book.begin_submission(PaperOrderDraft(original.client_order_id,
                                                       {"symbol":"ETH/USD"}), at=NOW)
            self.assertFalse(book.has_unresolved_provider_order())

    def test_provider_partial_then_terminal_must_reconcile_to_release_reserve(self):
        with PersistentPaperOrderStore(":memory:") as book:
            draft = book.journal.record(intent(1), portfolio(), checked_at=NOW, reference_price=Decimal("65000"))
            book.begin_submission(draft, at=NOW)
            book.observe_provider(BrokerObservation(draft.client_order_id, "provider1", "partially_filled",
                                                    Decimal("0.0001"), Decimal("65000")), at=NOW)
            book.observe_provider(BrokerObservation(draft.client_order_id, "provider1", "filled",
                                                    Decimal("0.00023"), Decimal("65100")), at=NOW)
            self.assertEqual(book.journal.total_reserved_usd(), Decimal("15"))
            with self.assertRaises(ValueError):
                book.finish_reconciliation(draft.client_order_id, at=NOW,
                                           provider_cash_verified=False, provider_position_verified=True,
                                           provider_order_verified=True)
            self.assertEqual(book.journal.total_reserved_usd(), Decimal("15"))
            closed = book.finish_reconciliation(draft.client_order_id, at=NOW,
                                                provider_cash_verified=True, provider_position_verified=True,
                                                provider_order_verified=True)
            self.assertEqual(closed.stage, Stage.RECONCILED)
            self.assertEqual(book.journal.total_reserved_usd(), Decimal("0"))
            self.assertFalse(book.has_unresolved_provider_order())
            # An old duplicate client ID is forever reserved, even after reconciliation.
            with self.assertRaises(ValueError):
                book.begin_submission(draft, at=NOW)

    def test_observations_append_events_but_cannot_rewrite_audit(self):
        with PersistentPaperOrderStore(":memory:") as book:
            d=book.journal.record(intent(1), portfolio(), checked_at=NOW, reference_price=Decimal("65000"))
            book.begin_submission(d, at=NOW)
            book.observe_provider(BrokerObservation(d.client_order_id,"provider1","accepted"), at=NOW)
            events=book.journal.recent_events()
            self.assertEqual([x["type"] for x in events],
                             ["DRAFT_APPROVED","SUBMISSION_PENDING","PROVIDER_OBSERVATION"])
            with self.assertRaises(Exception):
                book.connection.execute("UPDATE events SET event_type='FAKE' WHERE seq=1")


if __name__ == "__main__":
    unittest.main()

class RestartSafetyTests(unittest.TestCase):
    def test_pre_crash_pending_becomes_unknown_and_never_reposts(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "paper.db"
            with PersistentPaperOrderStore(path) as book:
                d = book.journal.record(intent(1), portfolio(), checked_at=NOW,
                                        reference_price=Decimal("65000"))
                book.begin_submission(d, at=NOW)
                # Emulate process crash before the HTTP response: close DB now.
            with PersistentPaperOrderStore(path) as book:
                self.assertEqual(book.recover_inflight_pending_after_restart(at=NOW), (d.client_order_id,))
                self.assertEqual(book.get(d.client_order_id).stage, Stage.UNKNOWN_RESULT)
                self.assertEqual(book.recover_inflight_pending_after_restart(at=NOW), ())
                self.assertEqual(book.journal.total_reserved_usd(), Decimal("15"))
                with self.assertRaises(ValueError):
                    book.begin_submission(d, at=NOW)

class LogicalDraftBridgeTests(unittest.TestCase):
    def test_verified_logical_gain_can_record_without_using_provider_balance(self):
        from datetime import datetime, timezone
        from decimal import Decimal
        from signal_vault.domain import Side, TradeIntent
        now = datetime(2026, 9, 29, 0, 0, tzinfo=timezone.utc)
        with PersistentPaperOrderStore(":memory:") as store:
            # Create a legitimate logical mark > $100 by directly representing a
            # previously reconciled inventory in the internal ledger for this unit test.
            store.connection.execute("UPDATE logical_portfolio SET cash_usd='90',btc_qty='0.0002',btc_cost_basis_usd='10' WHERE singleton=1")
            p = store.mark_portfolio(mark_price=Decimal("60000"), at=now)
            self.assertEqual(p.equity_usd, Decimal("102.0000"))
            intent = TradeIntent("crypto", "alpaca", "BTC/USD", Side.SELL, Decimal("12"),
                                 "gain-verified", "sig-gain-sell", now)
            draft = store.record_logical_draft(intent, p, checked_at=now,
                                                reference_price=Decimal("60000"),
                                                full_sell_quantity=Decimal("0.0002"))
            self.assertEqual(draft.payload["side"], "sell")

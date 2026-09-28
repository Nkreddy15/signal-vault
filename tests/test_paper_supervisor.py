import unittest
from datetime import datetime, timezone
from decimal import Decimal

from signal_vault.alpaca_paper import PaperAlpacaReadClient, build_non_executable_draft
from signal_vault.domain import PortfolioSnapshot, Side, TradeIntent
from signal_vault.paper_executor import PaperOnceExecutor
from signal_vault.paper_order_state import Stage
from signal_vault.paper_store import PersistentPaperOrderStore
from signal_vault.paper_supervisor import PaperRecoverySupervisor

NOW = datetime(2026, 9, 28, 22, 0, tzinfo=timezone.utc)


def make_draft(store, order_id="sv-recover-1"):
    intent = TradeIntent("crypto", "alpaca", "BTC/USD", Side.BUY, Decimal("15"),
                         order_id, "evidence-recover", NOW)
    portfolio = PortfolioSnapshot(Decimal("100"), Decimal("100"), Decimal("100"), Decimal("100"))
    draft = build_non_executable_draft(intent, portfolio, checked_at=NOW,
                                       reference_price=Decimal("65000"))
    store.journal.record(intent, portfolio, checked_at=NOW, reference_price=Decimal("65000"))
    return draft


class PaperSupervisorTests(unittest.TestCase):
    def test_restart_pending_becomes_unknown_and_uses_lookup_not_post(self):
        with PersistentPaperOrderStore(":memory:") as store:
            draft = make_draft(store)
            store.begin_submission(draft, at=NOW)  # simulate crash before HTTP result recorded
            post_calls = []
            executor = PaperOnceExecutor(paper_key="p", paper_secret="s", store=store,
                                         transport=lambda *_: post_calls.append(1))
            reader = PaperAlpacaReadClient("p", "s", transport=lambda *_: {
                "id": "provider-1", "client_order_id": draft.client_order_id,
                "status": "accepted", "filled_qty": "0", "filled_avg_price": None,
            })
            report = PaperRecoverySupervisor(store=store, executor=executor, reader=reader).recover_once(at=NOW)
            self.assertFalse(report.safe_for_new_submission)
            self.assertEqual(report.items[0].before, Stage.UNKNOWN_RESULT)
            self.assertEqual(report.items[0].after, Stage.BROKER_ACCEPTED)
            self.assertEqual(post_calls, [])

    def test_terminal_order_stays_blocked_until_independent_audit(self):
        with PersistentPaperOrderStore(":memory:") as store:
            draft = make_draft(store)
            executor = PaperOnceExecutor(paper_key="p", paper_secret="s", store=store,
                                         transport=lambda *_: {
                    "id": "provider-1", "client_order_id": draft.client_order_id,
                    "status": "filled", "filled_qty": "0.00023", "filled_avg_price": "65000"})
            self.assertEqual(executor.submit_once(draft, at=NOW).stage,
                             Stage.BROKER_TERMINAL_UNRECONCILED)
            reader = PaperAlpacaReadClient("p", "s", transport=lambda *_: {"found": False})
            report = PaperRecoverySupervisor(store=store, executor=executor, reader=reader).recover_once(at=NOW)
            self.assertFalse(report.safe_for_new_submission)
            self.assertEqual(report.items[0].action, "await_independent_reconciliation")
            self.assertEqual(store.get(draft.client_order_id).stage, Stage.BROKER_TERMINAL_UNRECONCILED)

    def test_reconciled_book_is_safe_without_network_action(self):
        with PersistentPaperOrderStore(":memory:") as store:
            draft = make_draft(store)
            executor = PaperOnceExecutor(paper_key="p", paper_secret="s", store=store,
                                         transport=lambda *_: {
                    "id": "provider-1", "client_order_id": draft.client_order_id,
                    "status": "canceled", "filled_qty": "0", "filled_avg_price": None})
            executor.submit_once(draft, at=NOW)
            store.finish_reconciliation(draft.client_order_id, at=NOW,
                                        provider_cash_verified=True,
                                        provider_position_verified=True,
                                        provider_order_verified=True)
            reader = PaperAlpacaReadClient("p", "s", transport=lambda *_: {"found": False})
            report = PaperRecoverySupervisor(store=store, executor=executor, reader=reader).recover_once(at=NOW)
            self.assertTrue(report.safe_for_new_submission)
            self.assertEqual(report.items[0].action, "already_reconciled")

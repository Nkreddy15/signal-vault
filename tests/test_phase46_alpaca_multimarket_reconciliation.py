import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.multimarket_alpaca_reconciliation import (
    alpaca_paper_lookup_observation,
    reconcile_alpaca_paper_order_lookup,
)
from signal_vault.multimarket_execution_journal import (
    MultiMarketExecutionJournal,
    MultiMarketOrderDraft,
)
from signal_vault.multimarket_paper_router import route_paper_execution
from signal_vault.paper_order_state import Stage

NOW = datetime(2026, 9, 30, 19, 30, tzinfo=timezone.utc)


class FakeReader:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def lookup_order(self, client_order_id):
        self.calls.append(client_order_id)
        return self.response


def draft(client_id="eq_123", lane="us_equity", instrument="AAPL"):
    payload = {
        "symbol": instrument,
        "side": "buy",
        "type": "market",
        "time_in_force": "day" if lane == "us_equity" else "gtc",
        "client_order_id": client_id,
        "notional": "10",
    }
    return MultiMarketOrderDraft(
        client_order_id=client_id,
        market_lane=lane,
        instrument=instrument,
        max_loss_usd=Decimal("10"),
        payload=payload,
    )


class AlpacaMultiMarketReconciliationTests(unittest.TestCase):
    def make_journal(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        journal = MultiMarketExecutionJournal(Path(tmp.name) / "mm.sqlite3")
        self.addCleanup(journal.close)
        return journal

    def start(self, journal, item):
        journal.record_approved_draft(item, at=NOW)
        journal.begin_submission(item, at=NOW)

    def test_lookup_safe_id_limit_is_enforced_before_route(self):
        item = draft(client_id="x" * 49)
        risk = {
            "kind": "CROSS_MARKET_RISK_ASSESSMENT_NOT_ORDER_AUTHORIZATION",
            "lane": "us_equity",
            "risk_admissible": True,
            "assessment_is_not_trading_authorization": True,
            "automatic_order_submission": "DISABLED",
        }
        with self.assertRaises(ValueError):
            route_paper_execution(item, risk_assessment=risk)

    def test_missing_lookup_after_pending_becomes_unknown_and_stays_blocking(self):
        journal = self.make_journal()
        item = draft()
        self.start(journal, item)
        reader = FakeReader(None)

        outcome = reconcile_alpaca_paper_order_lookup(
            journal=journal,
            reader=reader,
            client_order_id=item.client_order_id,
            expected_instrument=item.instrument,
            at=NOW,
        )
        self.assertEqual(outcome.state.stage, Stage.UNKNOWN_RESULT)
        self.assertTrue(outcome.new_execution_blocked)
        self.assertFalse(outcome.lookup_found)
        self.assertEqual(reader.calls, [item.client_order_id])

    def test_partial_fill_lookup_updates_shared_journal_without_unblocking(self):
        journal = self.make_journal()
        item = draft()
        self.start(journal, item)
        response = {
            "id": "paper-order-1",
            "client_order_id": item.client_order_id,
            "symbol": "AAPL",
            "status": "partially_filled",
            "filled_qty": "0.25",
            "filled_avg_price": "201.50",
        }
        outcome = reconcile_alpaca_paper_order_lookup(
            journal=journal,
            reader=FakeReader(response),
            client_order_id=item.client_order_id,
            expected_instrument="AAPL",
            at=NOW,
        )
        self.assertEqual(outcome.state.stage, Stage.PARTIALLY_FILLED)
        self.assertEqual(outcome.state.cumulative_filled_qty, Decimal("0.25"))
        self.assertTrue(outcome.new_execution_blocked)
        self.assertFalse(outcome.full_account_reconciliation_still_required)

    def test_filled_lookup_is_terminal_but_not_fully_reconciled(self):
        journal = self.make_journal()
        item = draft(lane="crypto", instrument="BTC/USD", client_id="btc_123")
        self.start(journal, item)
        response = {
            "id": "paper-order-2",
            "client_order_id": item.client_order_id,
            "symbol": "BTC/USD",
            "status": "filled",
            "filled_qty": "0.0002",
            "filled_avg_price": "65000",
        }
        outcome = reconcile_alpaca_paper_order_lookup(
            journal=journal,
            reader=FakeReader(response),
            client_order_id=item.client_order_id,
            expected_instrument="BTC/USD",
            at=NOW,
        )
        self.assertEqual(outcome.state.stage, Stage.BROKER_TERMINAL_UNRECONCILED)
        self.assertTrue(outcome.provider_terminal)
        self.assertTrue(outcome.full_account_reconciliation_still_required)
        self.assertTrue(outcome.new_execution_blocked)

    def test_wrong_symbol_or_client_id_is_rejected(self):
        base = {
            "id": "paper-order-3",
            "client_order_id": "eq_123",
            "symbol": "AAPL",
            "status": "new",
            "filled_qty": "0",
            "filled_avg_price": None,
        }
        for changed in (
            {**base, "symbol": "MSFT"},
            {**base, "client_order_id": "other"},
        ):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                alpaca_paper_lookup_observation(
                    changed,
                    expected_client_order_id="eq_123",
                    expected_instrument="AAPL",
                )


if __name__ == "__main__":
    unittest.main()

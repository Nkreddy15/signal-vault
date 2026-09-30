"""Provider-neutral execution journal tests, entirely offline."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.multimarket_execution_journal import (
    MultiMarketExecutionJournal,MultiMarketOrderDraft,
)
from signal_vault.paper_order_state import BrokerObservation,Stage

NOW=datetime(2026,9,30,tzinfo=timezone.utc)

def draft(client,lane,instrument):
    return MultiMarketOrderDraft(
        client_order_id=client,market_lane=lane,instrument=instrument,
        max_loss_usd=Decimal("5"),
        payload={"instrument":instrument,"side":"buy","client_order_id":client})

class MultiMarketJournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"journal.sqlite3"

    def test_one_unresolved_order_blocks_every_market_lane(self):
        with MultiMarketExecutionJournal(self.path) as store:
            a=draft("stock1","us_equity","AAPL")
            b=draft("kalshi1","kalshi_event_contract","KXTEST")
            store.record_approved_draft(a,at=NOW)
            store.record_approved_draft(b,at=NOW)
            self.assertEqual(store.begin_submission(a,at=NOW).stage,Stage.SUBMISSION_PENDING)
            with self.assertRaises(PermissionError):
                store.begin_submission(b,at=NOW)

    def test_restart_pending_becomes_unknown_never_safe_to_retry(self):
        a=draft("crypto1","crypto","BTC/USD")
        with MultiMarketExecutionJournal(self.path) as store:
            store.record_approved_draft(a,at=NOW)
            store.begin_submission(a,at=NOW)
        with MultiMarketExecutionJournal(self.path) as store:
            changed=store.recover_pending_after_restart(at=NOW)
            self.assertEqual(changed,("crypto1",))
            self.assertEqual(store.get_state("crypto1").stage,Stage.UNKNOWN_RESULT)
            with self.assertRaises(ValueError):
                store.begin_submission(a,at=NOW)

    def test_provider_terminal_requires_full_reconciliation_before_unblock(self):
        a=draft("event1","kalshi_event_contract","KXTEST")
        b=draft("stock2","us_equity","SPY")
        with MultiMarketExecutionJournal(self.path) as store:
            store.record_approved_draft(a,at=NOW)
            store.record_approved_draft(b,at=NOW)
            store.begin_submission(a,at=NOW)
            state=store.observe_provider(BrokerObservation(
                "event1","provider-1","filled",Decimal("1"),Decimal("0.55")),at=NOW)
            self.assertEqual(state.stage,Stage.BROKER_TERMINAL_UNRECONCILED)
            with self.assertRaises(PermissionError):
                store.begin_submission(b,at=NOW)
            state=store.confirm_reconciled(
                "event1",at=NOW,provider_cash_verified=True,
                provider_position_verified=True,provider_order_verified=True)
            self.assertEqual(state.stage,Stage.RECONCILED)
            self.assertEqual(store.begin_submission(b,at=NOW).stage,Stage.SUBMISSION_PENDING)

    def test_payload_identity_and_credentials_fail_closed(self):
        with self.assertRaises(ValueError):
            MultiMarketOrderDraft(
                "bad","us_equity","AAPL",Decimal("5"),
                {"api_key":"secret","side":"buy"})
        with MultiMarketExecutionJournal(self.path) as store:
            a=draft("stock3","us_equity","MSFT")
            store.record_approved_draft(a,at=NOW)
            altered=MultiMarketOrderDraft(
                "stock3","us_equity","MSFT",Decimal("5"),
                {"instrument":"MSFT","side":"sell","client_order_id":"stock3"})
            with self.assertRaises(PermissionError):
                store.begin_submission(altered,at=NOW)

if __name__=="__main__":
    unittest.main()

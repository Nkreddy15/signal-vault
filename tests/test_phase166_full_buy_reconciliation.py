import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from decimal import Decimal

from signal_vault.experimental_paper_reconcile import reconcile_experimental_paper
from signal_vault.multimarket_execution_journal import MultiMarketExecutionJournal, MultiMarketOrderDraft
from signal_vault.paper_credentials import PaperCredentials
from signal_vault.paper_order_state import BrokerObservation


class Reader:
    def __init__(self,*args,**kwargs): pass
    def lookup_order(self,client_order_id):
        return {
            "id":"12345678-1234-1234-1234-123456789abc",
            "client_order_id":client_order_id,
            "symbol":"BTC/USD",
            "status":"filled",
            "filled_qty":"0.000117",
            "filled_avg_price":"85470.08",
        }
    def get_account(self):
        return {"status":"ACTIVE","trading_blocked":False,"equity":"100000"}
    def get_positions(self):
        return ({"symbol":"BTCUSD","qty":"0.000117"},)
    def get_open_orders(self): return ()


class Phase166FullBuyReconciliationTests(unittest.TestCase):
    def test_filled_buy_reconciles_against_exact_btc_position(self):
        now=datetime(2026,10,2,18,0,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"journal.sqlite3"
            client_id="svexp-testbuy123"
            draft=MultiMarketOrderDraft(
                client_id,"crypto","BTC/USD",Decimal("10"),
                {
                    "symbol":"BTC/USD","side":"buy","type":"market",
                    "time_in_force":"gtc","client_order_id":client_id,
                    "notional":"10",
                },
            )
            with MultiMarketExecutionJournal(p) as journal:
                journal.record_approved_draft(draft,at=now)
                journal.begin_submission(draft,at=now)
                journal.observe_provider(
                    BrokerObservation(
                        client_id,
                        "12345678-1234-1234-1234-123456789abc",
                        "filled",
                        Decimal("0.000117"),
                        Decimal("85470.08"),
                    ),
                    at=now,
                )
            source={
                "kind":"EXPERIMENTAL_SUPERVISED_BTC_PAPER_SANDBOX",
                "experimental_only":True,
                "strategy_validated":False,
                "live_trading":"UNAVAILABLE",
                "paper_post_attempted":True,
                "paper_order_submission":"ATTEMPT_RECORDED",
                "client_order_id":client_id,
            }
            out=reconcile_experimental_paper(
                source_receipt=source,
                journal_path=p,
                credentials=PaperCredentials("paper-key","paper-secret"),
                at=now,
                reader_factory=Reader,
            )
            self.assertEqual(out["journal_stage"],"reconciled")
            self.assertTrue(out["journal_reconciled"])
            self.assertEqual(out["btc_position_qty"],"0.000117")
            self.assertEqual(out["open_order_count"],0)
            self.assertEqual(out["next_action"],"PAPER_POSITION_RECONCILED_CONTINUE_OBSERVATION")
            self.assertEqual(out["order_submission"],"DISABLED")


if __name__=="__main__":
    unittest.main()

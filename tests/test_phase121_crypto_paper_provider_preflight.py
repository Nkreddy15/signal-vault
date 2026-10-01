import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.crypto_paper_executor_draft import KIND as PREPARED_KIND
from signal_vault.crypto_paper_provider_preflight import (
    KIND,
    capture_crypto_paper_provider_preflight,
)
from signal_vault.multimarket_execution_journal import (
    MultiMarketExecutionJournal,
    MultiMarketOrderDraft,
)


UTC=timezone.utc
NOW=datetime(2026,10,1,7,45,tzinfo=UTC)
CLIENT_ID="svp-phase121-test"
PAYLOAD={
    "symbol":"BTC/USD",
    "side":"buy",
    "type":"market",
    "time_in_force":"gtc",
    "client_order_id":CLIENT_ID,
    "notional":"5",
}


class Reader:
    def __init__(self, *, positions=(), open_orders=(), blocked=False):
        self.positions=positions
        self.open_orders=open_orders
        self.blocked=blocked
        self.calls=[]

    def get_account(self):
        self.calls.append("account")
        return {
            "status":"ACTIVE",
            "trading_blocked":self.blocked,
            "non_marginable_buying_power":"100000",
            "account_number":"must-not-be-persisted",
        }

    def get_btc_asset(self):
        self.calls.append("asset")
        return {
            "symbol":"BTC/USD",
            "class":"crypto",
            "status":"active",
            "tradable":True,
            "fractionable":True,
            "min_order_size":"0.0001",
            "min_trade_increment":"0.000000001",
            "price_increment":"0.01",
        }

    def get_positions(self):
        self.calls.append("positions")
        return tuple(self.positions)

    def get_open_orders(self):
        self.calls.append("open_orders")
        return tuple(self.open_orders)


class CryptoPaperProviderPreflightTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.journal=MultiMarketExecutionJournal(Path(temp.name)/"mm.sqlite3")
        self.addCleanup(self.journal.close)
        self.draft=MultiMarketOrderDraft(
            client_order_id=CLIENT_ID,
            market_lane="crypto",
            instrument="BTC/USD",
            max_loss_usd=Decimal("5"),
            payload=dict(PAYLOAD),
        )
        self.journal.record_approved_draft(self.draft,at=NOW)
        self.prepared={
            "kind":PREPARED_KIND,
            "status":"DURABLE_CRYPTO_PAPER_DRAFT_APPROVED_NOT_SUBMITTED",
            "decision_id":CLIENT_ID,
            "market_lane":"crypto",
            "instrument":"BTC/USD",
            "max_loss_usd":"5",
            "payload_sha256":self.draft.payload_sha256,
            "provider_post_attempted":False,
            "paper_executor_invoked":False,
            "paper_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        }

    def test_fresh_empty_paper_account_preflight_persists_before_submission(self):
        reader=Reader()
        result=capture_crypto_paper_provider_preflight(
            self.prepared,
            journal=self.journal,
            reader=reader,
            at=NOW,
        )
        self.assertEqual(result["kind"],KIND)
        self.assertEqual(result["status"],"FRESH_PROVIDER_PREFLIGHT_PERSISTED")
        self.assertEqual(
            reader.calls,["account","asset","positions","open_orders"]
        )
        self.assertFalse(result["provider_post_attempted"])
        self.assertEqual(result["paper_order_submission"],"DISABLED")
        self.assertEqual(result["live_trading"],"UNAVAILABLE")
        self.assertEqual(result["provider_positions_count"],0)
        self.assertEqual(result["provider_open_orders_count"],0)
        self.assertNotIn("account_number",str(result))
        stored=self.journal.get_provider_preflight(CLIENT_ID)
        self.assertEqual(stored["decision_id"],CLIENT_ID)
        self.assertFalse(stored["credential_values_persisted"])
        with self.assertRaises(KeyError):
            self.journal.get_state(CLIENT_ID)

    def test_existing_position_or_open_order_blocks_without_preflight_receipt(self):
        for reader in (
            Reader(positions=({"symbol":"BTCUSD","qty":"0.1"},)),
            Reader(open_orders=({"id":"existing"},)),
        ):
            with self.subTest(reader=reader), self.assertRaises(PermissionError):
                capture_crypto_paper_provider_preflight(
                    self.prepared,
                    journal=self.journal,
                    reader=reader,
                    at=NOW,
                )
            with self.assertRaises(KeyError):
                self.journal.get_provider_preflight(CLIENT_ID)

    def test_blocked_account_fails_before_asset_or_portfolio_reads(self):
        reader=Reader(blocked=True)
        with self.assertRaises(PermissionError):
            capture_crypto_paper_provider_preflight(
                self.prepared,
                journal=self.journal,
                reader=reader,
                at=NOW,
            )
        self.assertEqual(reader.calls,["account"])
        with self.assertRaises(KeyError):
            self.journal.get_provider_preflight(CLIENT_ID)

    def test_preflight_cannot_be_written_after_submission_has_started(self):
        self.journal.begin_submission(self.draft,at=NOW)
        reader=Reader()
        with self.assertRaises(PermissionError):
            capture_crypto_paper_provider_preflight(
                self.prepared,
                journal=self.journal,
                reader=reader,
                at=NOW,
            )
        with self.assertRaises(KeyError):
            self.journal.get_provider_preflight(CLIENT_ID)

    def test_preflight_receipt_is_create_once(self):
        reader=Reader()
        capture_crypto_paper_provider_preflight(
            self.prepared,journal=self.journal,reader=reader,at=NOW
        )
        with self.assertRaises(Exception):
            capture_crypto_paper_provider_preflight(
                self.prepared,journal=self.journal,reader=Reader(),at=NOW
            )


if __name__=="__main__":
    unittest.main()

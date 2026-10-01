import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.crypto_paper_executor_draft import KIND as PREPARED_KIND
from signal_vault.crypto_paper_pilot_command import (
    KIND,
    _existing_journal_path,
    run_crypto_paper_pilot,
)
from signal_vault.crypto_paper_pilot_dry_run import KIND as DRY_RUN_KIND
from signal_vault.multimarket_execution_journal import (
    MultiMarketExecutionJournal,
    MultiMarketOrderDraft,
)
from signal_vault.multimarket_paper_router import CRYPTO_PAPER_ACK
from signal_vault.paper_credentials import PaperCredentials


UTC=timezone.utc
NOW=datetime(2026,10,1,10,0,tzinfo=UTC)
CLIENT_ID="svp-phase127-test"
PAYLOAD={
    "symbol":"BTC/USD",
    "side":"buy",
    "type":"market",
    "time_in_force":"gtc",
    "client_order_id":CLIENT_ID,
    "notional":"5",
}


class Reader:
    calls=0

    def __init__(self,key,secret):
        del key,secret

    def get_account(self):
        type(self).calls+=1
        return {
            "status":"ACTIVE",
            "trading_blocked":False,
            "non_marginable_buying_power":"100000",
        }

    def get_btc_asset(self):
        type(self).calls+=1
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
        type(self).calls+=1
        return ()

    def get_open_orders(self):
        type(self).calls+=1
        return ()


def risk():
    return {
        "kind":"CROSS_MARKET_RISK_ASSESSMENT_NOT_ORDER_AUTHORIZATION",
        "lane":"crypto",
        "proposed_max_loss_usd":"5",
        "risk_admissible":True,
        "rejection_reasons":[],
        "assessment_is_not_trading_authorization":True,
        "automatic_order_submission":"DISABLED",
    }


def dry_run():
    return {
        "kind":DRY_RUN_KIND,
        "status":"READY_FOR_SEPARATE_PAPER_EXECUTOR_INVOCATION_REVIEW",
        "eligible_for_separate_paper_executor_invocation_review":True,
        "paper_preview":{
            "decision_id":CLIENT_ID,
            "market_lane":"crypto",
            "instrument":"BTC/USD",
            "risk_assessment":risk(),
            "route":{
                "provider":"alpaca",
                "environment":"paper",
                "market_lane":"crypto",
                "required_acknowledgement":CRYPTO_PAPER_ACK,
                "live_trading_available":False,
                "payload":dict(PAYLOAD),
            },
        },
        "provider_post_attempted":False,
        "paper_executor_invoked":False,
        "paper_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


class CryptoPaperPilotCommandTests(unittest.TestCase):
    def setUp(self):
        Reader.calls=0
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.path=self.root/"execution.sqlite3"
        self.journal=MultiMarketExecutionJournal(self.path)
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
        self.credentials=PaperCredentials("paper-key","paper-secret")

    def test_default_mode_is_fresh_preflight_only_no_order_submission(self):
        result=run_crypto_paper_pilot(
            prepared=self.prepared,
            dry_run=dry_run(),
            journal=self.journal,
            credentials=self.credentials,
            execute=False,
            at=NOW,
            reader_factory=Reader,
        )
        self.assertEqual(result["kind"],KIND)
        self.assertEqual(
            result["status"],
            "PREFLIGHT_ONLY_COMPLETE_NO_ORDER_SUBMISSION",
        )
        self.assertEqual(Reader.calls,4)
        self.assertFalse(result["paper_post_attempted"])
        self.assertFalse(result["paper_executor_invoked"])
        self.assertEqual(result["paper_order_submission"],"DISABLED")
        self.assertEqual(result["live_trading"],"UNAVAILABLE")
        with self.assertRaises(KeyError):
            self.journal.get_state(CLIENT_ID)
        self.assertEqual(
            self.journal.get_provider_preflight(CLIENT_ID)["decision_id"],
            CLIENT_ID,
        )

    def test_explicit_execute_and_exact_ack_can_invoke_one_paper_post(self):
        posts=[]
        def transport(payload,key,secret):
            posts.append((dict(payload),key,secret))
            return {
                "client_order_id":CLIENT_ID,
                "id":"paper-order-phase127",
                "status":"accepted",
                "filled_qty":"0",
                "filled_avg_price":None,
            }

        result=run_crypto_paper_pilot(
            prepared=self.prepared,
            dry_run=dry_run(),
            journal=self.journal,
            credentials=self.credentials,
            execute=True,
            acknowledgement=CRYPTO_PAPER_ACK,
            at=NOW,
            reader_factory=Reader,
            execution_transport=transport,
        )
        self.assertEqual(result["status"],"ONE_SHOT_PAPER_EXECUTOR_INVOKED")
        self.assertTrue(result["paper_post_attempted"])
        self.assertTrue(result["paper_executor_invoked"])
        self.assertEqual(len(posts),1)
        self.assertEqual(posts[0][0],PAYLOAD)
        self.assertEqual(result["live_order_submission"],"UNAVAILABLE")

    def test_wrong_execute_ack_blocks_before_any_provider_read_or_post(self):
        posts=[]
        with self.assertRaises(PermissionError):
            run_crypto_paper_pilot(
                prepared=self.prepared,
                dry_run=dry_run(),
                journal=self.journal,
                credentials=self.credentials,
                execute=True,
                acknowledgement="WRONG",
                at=NOW,
                reader_factory=Reader,
                execution_transport=lambda *_:posts.append(True),
            )
        self.assertEqual(Reader.calls,0)
        self.assertEqual(posts,[])
        with self.assertRaises(KeyError):
            self.journal.get_provider_preflight(CLIENT_ID)
        with self.assertRaises(KeyError):
            self.journal.get_state(CLIENT_ID)

    def test_existing_preflight_is_refreshed_instead_of_dead_ending(self):
        first=run_crypto_paper_pilot(
            prepared=self.prepared,
            dry_run=dry_run(),
            journal=self.journal,
            credentials=self.credentials,
            execute=False,
            at=NOW,
            reader_factory=Reader,
        )
        second=run_crypto_paper_pilot(
            prepared=self.prepared,
            dry_run=dry_run(),
            journal=self.journal,
            credentials=self.credentials,
            execute=False,
            at=NOW.replace(minute=7),
            reader_factory=Reader,
        )
        self.assertFalse(first["provider_preflight_refreshed"])
        self.assertTrue(second["provider_preflight_refreshed"])
        history=self.journal.connection.execute(
            "SELECT count(*) FROM mm_execution_preflight_history "
            "WHERE client_order_id=?",
            (CLIENT_ID,),
        ).fetchone()[0]
        self.assertEqual(history,1)

    def test_cli_path_guard_never_creates_missing_execution_journal(self):
        missing=self.root/"missing.sqlite3"
        with self.assertRaises(ValueError):
            _existing_journal_path(missing)
        self.assertFalse(missing.exists())
        link=self.root/"link.sqlite3"
        link.symlink_to(self.path)
        with self.assertRaises(ValueError):
            _existing_journal_path(link)


if __name__=="__main__":
    unittest.main()

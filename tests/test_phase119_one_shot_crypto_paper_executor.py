import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.crypto_paper_executor_draft import KIND as PREPARED_KIND
from signal_vault.crypto_paper_executor_once import (
    KIND,
    execute_prepared_crypto_paper_once,
)
from signal_vault.crypto_paper_pilot_dry_run import KIND as DRY_RUN_KIND
from signal_vault.crypto_paper_provider_preflight import (
    capture_crypto_paper_provider_preflight,
)
from signal_vault.multimarket_execution_journal import (
    MultiMarketExecutionJournal,
    MultiMarketOrderDraft,
)
from signal_vault.multimarket_paper_router import CRYPTO_PAPER_ACK


UTC=timezone.utc
NOW=datetime(2026,10,1,7,30,tzinfo=UTC)
CLIENT_ID="svp-phase119-test"
PAYLOAD={
    "symbol":"BTC/USD",
    "side":"buy",
    "type":"market",
    "time_in_force":"gtc",
    "client_order_id":CLIENT_ID,
    "notional":"5",
}


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
        "live_trading":"UNAVAILABLE",
    }



class Reader:
    def get_account(self):
        return {
            "status":"ACTIVE",
            "trading_blocked":False,
            "non_marginable_buying_power":"100000",
        }

    def get_btc_asset(self):
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
        return ()

    def get_open_orders(self):
        return ()


class CryptoPaperExecutorOnceTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.journal=MultiMarketExecutionJournal(
            Path(temp.name)/"execution.sqlite3"
        )
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
        capture_crypto_paper_provider_preflight(
            self.prepared,
            journal=self.journal,
            reader=Reader(),
            at=NOW,
        )

    def test_exact_ack_executes_one_injected_paper_post_and_records_provider_state(self):
        calls=[]
        def transport(payload,key,secret):
            calls.append((dict(payload),key,secret))
            return {
                "client_order_id":CLIENT_ID,
                "id":"paper-order-phase119",
                "status":"accepted",
                "filled_qty":"0",
                "filled_avg_price":None,
            }

        result=execute_prepared_crypto_paper_once(
            self.prepared,
            dry_run(),
            journal=self.journal,
            paper_key="paper-key",
            paper_secret="paper-secret",
            acknowledgement=CRYPTO_PAPER_ACK,
            at=NOW,
            transport=transport,
        )
        self.assertEqual(result["kind"],KIND)
        self.assertEqual(result["environment"],"alpaca_paper")
        self.assertTrue(result["paper_post_attempted"])
        self.assertTrue(result["paper_executor_invoked"])
        self.assertFalse(result["live_host_available"])
        self.assertEqual(result["live_order_submission"],"UNAVAILABLE")
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][0],PAYLOAD)
        state=self.journal.get_state(CLIENT_ID)
        self.assertEqual(state.provider_status,"accepted")
        self.assertEqual(state.broker_order_id,"paper-order-phase119")

    def test_wrong_ack_blocks_before_transport_and_submission_state(self):
        calls=[]
        def transport(payload,key,secret):
            calls.append(True)
            raise AssertionError("must not be called")

        with self.assertRaises(PermissionError):
            execute_prepared_crypto_paper_once(
                self.prepared,
                dry_run(),
                journal=self.journal,
                paper_key="paper-key",
                paper_secret="paper-secret",
                acknowledgement="WRONG",
                at=NOW,
                transport=transport,
            )
        self.assertEqual(calls,[])
        with self.assertRaises(KeyError):
            self.journal.get_state(CLIENT_ID)

    def test_transport_uncertainty_becomes_unknown_and_never_blind_retries(self):
        def uncertain(payload,key,secret):
            raise TimeoutError("synthetic uncertainty")

        result=execute_prepared_crypto_paper_once(
            self.prepared,
            dry_run(),
            journal=self.journal,
            paper_key="paper-key",
            paper_secret="paper-secret",
            acknowledgement=CRYPTO_PAPER_ACK,
            at=NOW,
            transport=uncertain,
        )
        self.assertEqual(result["stage"],"unknown_result")
        self.assertTrue(result["blind_retry_forbidden"])
        self.assertTrue(self.journal.has_unresolved())

        with self.assertRaises((PermissionError,ValueError)):
            execute_prepared_crypto_paper_once(
                self.prepared,
                dry_run(),
                journal=self.journal,
                paper_key="paper-key",
                paper_secret="paper-secret",
                acknowledgement=CRYPTO_PAPER_ACK,
                at=NOW,
                transport=uncertain,
            )

    def test_receipt_mismatch_blocks_before_transport(self):
        bad=dict(self.prepared)
        bad["payload_sha256"]="0"*64
        calls=[]
        with self.assertRaises(ValueError):
            execute_prepared_crypto_paper_once(
                bad,
                dry_run(),
                journal=self.journal,
                paper_key="paper-key",
                paper_secret="paper-secret",
                acknowledgement=CRYPTO_PAPER_ACK,
                at=NOW,
                transport=lambda *_:calls.append(True),
            )
        self.assertEqual(calls,[])


    def test_missing_provider_preflight_blocks_before_transport(self):
        with tempfile.TemporaryDirectory() as td:
            journal=MultiMarketExecutionJournal(Path(td)/"missing.sqlite3")
            self.addCleanup(journal.close)
            journal.record_approved_draft(self.draft,at=NOW)
            calls=[]
            with self.assertRaises(KeyError):
                execute_prepared_crypto_paper_once(
                    self.prepared,
                    dry_run(),
                    journal=journal,
                    paper_key="paper-key",
                    paper_secret="paper-secret",
                    acknowledgement=CRYPTO_PAPER_ACK,
                    at=NOW,
                    transport=lambda *_:calls.append(True),
                )
            self.assertEqual(calls,[])

    def test_stale_provider_preflight_blocks_before_transport(self):
        calls=[]
        with self.assertRaises(PermissionError):
            execute_prepared_crypto_paper_once(
                self.prepared,
                dry_run(),
                journal=self.journal,
                paper_key="paper-key",
                paper_secret="paper-secret",
                acknowledgement=CRYPTO_PAPER_ACK,
                at=NOW+timedelta(minutes=6),
                transport=lambda *_:calls.append(True),
            )
        self.assertEqual(calls,[])
        with self.assertRaises(KeyError):
            self.journal.get_state(CLIENT_ID)


if __name__=="__main__":
    unittest.main()

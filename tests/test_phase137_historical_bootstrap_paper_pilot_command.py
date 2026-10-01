import hashlib
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.historical_bootstrap_paper_draft import (
    persist_bootstrap_crypto_paper_draft,
)
from signal_vault.historical_bootstrap_paper_pilot_command import (
    KIND,
    run_bootstrap_crypto_paper_pilot,
)
from signal_vault.historical_bootstrap_supervised_paper import (
    VALIDATION_KIND,
    build_supervised_bootstrap_paper_preview,
)
from signal_vault.multimarket_execution_journal import MultiMarketExecutionJournal
from signal_vault.multimarket_paper_router import CRYPTO_PAPER_ACK
from signal_vault.paper_credentials import PaperCredentials


NOW=datetime(2026,10,1,20,0,tzinfo=timezone.utc)
STRATEGY="generic-ema12x26-v1-predeclared"


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


def validation():
    raw={
        "kind":VALIDATION_KIND,
        "symbols":["AVAX/USD","BTC/USD","ETH/USD","LINK/USD","LTC/USD","SOL/USD"],
        "historical_hours":144,
        "chronological_fold_count":3,
        "selected_strategy":STRATEGY,
        "strictly_chronological":True,
        "selection_used_validation_only":True,
        "untouched_test_used_only_as_veto":True,
        "test_used_for_tuning":False,
        "historical_data_is_not_prospective_validation":True,
        "cost_stress_passes":{
            "illustrative_low_friction":True,
            "illustrative_base_friction":True,
            "illustrative_high_friction":True,
        },
        "broker_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
    raw["receipt_sha256"]=hashlib.sha256(repr(sorted(raw.items())).encode()).hexdigest()
    return raw


def shadow():
    symbols=["AVAX/USD","BTC/USD","ETH/USD","LINK/USD","LTC/USD","SOL/USD"]
    decisions={}
    for s in symbols:
        action="buy" if s=="BTC/USD" else "hold"
        decisions[s]={STRATEGY:{"flat":{
            "hypothetical_action":action,
            "evidence_sha256":hashlib.sha256((s+action).encode()).hexdigest(),
        }}}
    return {
        "kind":"OFFLINE_SIX_CRYPTO_SHA_CHAINED_SHADOW_ONLY",
        "broker_order_submission":"DISABLED",
        "automatic_paper_trading":"DISABLED",
        "live_trading":"UNAVAILABLE",
        "strategy_promoted":False,
        "future_edge_established":False,
        "latest_newly_observed_UTC_close":"2026-10-01T19:00:00+00:00",
        "shadow_payload_sha256":hashlib.sha256(b"shadow").hexdigest(),
        "predeclared_flat_and_held_hypothetical_decisions":decisions,
    }


def account():
    return {
        "exposure_by_lane":{"crypto":"0","us_equity":"0","kalshi_event_contract":"0"},
        "open_positions":0,
        "marked_equity_usd":"100",
        "daily_anchor_equity_usd":"100",
        "peak_equity_usd":"100",
        "operator_halted":False,
    }


class HistoricalBootstrapPaperPilotCommandTests(unittest.TestCase):
    def setUp(self):
        Reader.calls=0
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.journal=MultiMarketExecutionJournal(self.root/"execution.sqlite3")
        self.addCleanup(self.journal.close)
        self.preview=build_supervised_bootstrap_paper_preview(
            validation(),shadow(),account_state=account(),max_loss_usd="2"
        )
        self.prepared=persist_bootstrap_crypto_paper_draft(
            self.preview,journal=self.journal,at=NOW
        )
        self.credentials=PaperCredentials("paper-key","paper-secret")

    def test_default_mode_is_fresh_preflight_only(self):
        result=run_bootstrap_crypto_paper_pilot(
            prepared=self.prepared,
            bootstrap_preview=self.preview,
            journal=self.journal,
            credentials=self.credentials,
            execute=False,
            at=NOW,
            reader_factory=Reader,
        )
        self.assertEqual(result["kind"],KIND)
        self.assertEqual(result["status"],"PREFLIGHT_ONLY_COMPLETE_NO_ORDER_SUBMISSION")
        self.assertEqual(Reader.calls,4)
        self.assertFalse(result["paper_post_attempted"])
        self.assertFalse(result["paper_executor_invoked"])
        self.assertFalse(result["independent_prospective_gate_passed"])
        self.assertTrue(result["paper_period_is_forward_validation"])
        self.assertEqual(result["live_trading"],"UNAVAILABLE")

    def test_explicit_execute_and_exact_ack_can_invoke_one_paper_post(self):
        posts=[]
        def transport(payload,key,secret):
            posts.append((dict(payload),key,secret))
            return {
                "client_order_id":self.prepared["decision_id"],
                "id":"paper-order-bootstrap-test",
                "status":"accepted",
                "filled_qty":"0",
                "filled_avg_price":None,
            }

        result=run_bootstrap_crypto_paper_pilot(
            prepared=self.prepared,
            bootstrap_preview=self.preview,
            journal=self.journal,
            credentials=self.credentials,
            execute=True,
            acknowledgement=CRYPTO_PAPER_ACK,
            at=NOW,
            reader_factory=Reader,
            execution_transport=transport,
        )
        self.assertEqual(
            result["status"],
            "ONE_SHOT_SUPERVISED_BOOTSTRAP_PAPER_EXECUTOR_INVOKED",
        )
        self.assertEqual(len(posts),1)
        self.assertTrue(result["paper_post_attempted"])
        self.assertTrue(result["paper_executor_invoked"])
        self.assertFalse(result["independent_prospective_gate_passed"])
        self.assertEqual(result["live_order_submission"],"UNAVAILABLE")

    def test_wrong_ack_blocks_before_provider_reads_or_post(self):
        posts=[]
        with self.assertRaises(PermissionError):
            run_bootstrap_crypto_paper_pilot(
                prepared=self.prepared,
                bootstrap_preview=self.preview,
                journal=self.journal,
                credentials=self.credentials,
                execute=True,
                acknowledgement="WRONG",
                at=NOW,
                reader_factory=Reader,
                execution_transport=lambda *args:posts.append(args),
            )
        self.assertEqual(Reader.calls,0)
        self.assertEqual(posts,[])

    def test_preview_payload_tamper_blocks_before_provider_reads(self):
        bad=dict(self.preview)
        bad["paper_preview"]=dict(self.preview["paper_preview"])
        bad["paper_preview"]["route"]=dict(self.preview["paper_preview"]["route"])
        bad["paper_preview"]["route"]["payload"]=dict(
            self.preview["paper_preview"]["route"]["payload"]
        )
        bad["paper_preview"]["route"]["payload"]["notional"]="3"
        with self.assertRaises(ValueError):
            run_bootstrap_crypto_paper_pilot(
                prepared=self.prepared,
                bootstrap_preview=bad,
                journal=self.journal,
                credentials=self.credentials,
                execute=False,
                at=NOW,
                reader_factory=Reader,
            )
        self.assertEqual(Reader.calls,0)


if __name__=="__main__":
    unittest.main()

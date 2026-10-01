import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.crypto_paper_activation_handoff import (
    AUTH_ENVIRONMENT,
    AUTH_KIND,
    AUTH_SCOPE,
)
from signal_vault.crypto_paper_executor_draft import (
    KIND,
    persist_crypto_paper_executor_draft,
)
from signal_vault.crypto_paper_pilot_dry_run import run_crypto_paper_pilot_dry_run
from signal_vault.crypto_paper_pilot_review import ENGINEERING_KIND
from signal_vault.multimarket_execution_journal import (
    MultiMarketExecutionJournal,
    MultiMarketOrderDraft,
)
from signal_vault.multimarket_paper_router import CRYPTO_PAPER_ACK


UTC=timezone.utc
NOW=datetime(2026,10,1,7,0,tzinfo=UTC)
STRATEGY="generic-ema12x26-v1-predeclared"


def _forward_review():
    return {
        "kind":"PREDECLARED_SIX_CRYPTO_FORWARD_REVIEW_GATE_NOT_TRADING_AUTHORIZATION",
        "evidence_window_complete_for_gate":True,
        "candidates_meeting_all_review_criteria":[STRATEGY],
        "candidate_order_has_no_rank_or_preference":True,
        "automatic_candidate_selection":"DISABLED",
        "paper_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
        "separate_owner_authorization_still_required_for_any_PAPER_execution":True,
    }


def _engineering():
    return {
        "kind":ENGINEERING_KIND,
        "environment":"alpaca_paper",
        "live_host_requests":0,
        "paper_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "supervised_paper_smoke_reconciled":True,
        "paper_host_only_verified":True,
        "fresh_provider_preflight_passed":True,
        "durable_commit_before_post_validated":True,
        "duplicate_submission_prevention_validated":True,
        "unknown_result_recovery_validated":True,
        "provider_reconciliation_path_validated":True,
        "shared_cross_market_risk_governor_validated":True,
        "unresolved_paper_orders":0,
        "operator_halted":False,
    }


def _shadow():
    signals={}
    for index,symbol in enumerate(("BTC/USD","ETH/USD","SOL/USD")):
        signals[symbol]={
            STRATEGY:{
                "flat":{
                    "hypothetical_action":"buy" if symbol=="BTC/USD" else "hold",
                    "evidence_sha256":format(index+1,"064x"),
                },
                "already_held":{
                    "hypothetical_action":"hold",
                    "evidence_sha256":format(index+100,"064x"),
                },
            }
        }
    return {
        "kind":"OFFLINE_SIX_CRYPTO_SHA_CHAINED_SHADOW_ONLY",
        "latest_newly_observed_UTC_close":"2026-10-01T06:00:00+00:00",
        "shadow_payload_sha256":"d"*64,
        "predeclared_flat_and_held_hypothetical_decisions":signals,
        "broker_order_submission":"DISABLED",
        "automatic_paper_trading":"DISABLED",
        "live_trading":"UNAVAILABLE",
        "strategy_promoted":False,
        "future_edge_established":False,
    }


def _account():
    return {
        "exposure_by_lane":{
            "crypto":"0",
            "us_equity":"0",
            "kalshi_event_contract":"0",
        },
        "open_positions":0,
        "marked_equity_usd":"100",
        "daily_anchor_equity_usd":"100",
        "peak_equity_usd":"100",
        "operator_halted":False,
    }


def _owner():
    return {
        "kind":AUTH_KIND,
        "scope":AUTH_SCOPE,
        "environment":AUTH_ENVIRONMENT,
        "authorized":True,
        "max_single_order_loss_usd":"5",
        "live_trading_authorized":False,
    }


def _dry_run():
    return run_crypto_paper_pilot_dry_run(
        forward_review=_forward_review(),
        engineering_evidence=_engineering(),
        latest_shadow=_shadow(),
        account_state=_account(),
        owner_authorization=_owner(),
        max_loss_usd="5",
    )


class CryptoPaperExecutorDraftTests(unittest.TestCase):
    def make_journal(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path=Path(temp.name)/"execution.sqlite3"
        journal=MultiMarketExecutionJournal(path)
        self.addCleanup(journal.close)
        return journal

    def test_ready_dry_run_persists_one_approved_draft_without_submission(self):
        journal=self.make_journal()
        result=persist_crypto_paper_executor_draft(
            _dry_run(),
            journal=journal,
            at=NOW,
        )
        self.assertEqual(result["kind"],KIND)
        self.assertEqual(
            result["status"],
            "DURABLE_CRYPTO_PAPER_DRAFT_APPROVED_NOT_SUBMITTED",
        )
        self.assertEqual(result["market_lane"],"crypto")
        self.assertEqual(result["instrument"],"BTC/USD")
        self.assertEqual(result["max_loss_usd"],"5")
        self.assertEqual(result["required_acknowledgement"],CRYPTO_PAPER_ACK)
        self.assertTrue(result["execution_journal_write_performed"])
        self.assertFalse(result["provider_post_attempted"])
        self.assertFalse(result["paper_executor_invoked"])
        self.assertEqual(result["network_requests"],"NONE")
        self.assertEqual(result["credentials_accessed"],"NONE")
        self.assertEqual(result["paper_order_submission"],"DISABLED")
        self.assertEqual(result["live_trading"],"UNAVAILABLE")

        drafts=tuple(journal.connection.execute(
            "SELECT client_order_id,market_lane,instrument,status "
            "FROM mm_execution_drafts"
        ))
        states=tuple(journal.connection.execute(
            "SELECT client_order_id FROM mm_execution_states"
        ))
        self.assertEqual(len(drafts),1)
        self.assertEqual(drafts[0][1:],
                         ("crypto","BTC/USD","DRAFT_APPROVED"))
        self.assertEqual(states,())

    def test_tampered_route_ack_fails_before_journal_write(self):
        journal=self.make_journal()
        raw=_dry_run()
        raw["paper_preview"]["route"]["required_acknowledgement"]="WRONG"
        with self.assertRaises(ValueError):
            persist_crypto_paper_executor_draft(raw,journal=journal,at=NOW)
        count=journal.connection.execute(
            "SELECT COUNT(*) FROM mm_execution_drafts"
        ).fetchone()[0]
        self.assertEqual(count,0)

    def test_ineligible_dry_run_fails_before_journal_write(self):
        journal=self.make_journal()
        raw=_dry_run()
        raw["eligible_for_separate_paper_executor_invocation_review"]=False
        with self.assertRaises(ValueError):
            persist_crypto_paper_executor_draft(raw,journal=journal,at=NOW)
        count=journal.connection.execute(
            "SELECT COUNT(*) FROM mm_execution_drafts"
        ).fetchone()[0]
        self.assertEqual(count,0)

    def test_unresolved_cross_market_order_blocks_new_draft(self):
        journal=self.make_journal()
        existing=MultiMarketOrderDraft(
            client_order_id="existing-paper-order",
            market_lane="crypto",
            instrument="BTC/USD",
            max_loss_usd=Decimal("5"),
            payload={
                "symbol":"BTC/USD",
                "side":"buy",
                "type":"market",
                "time_in_force":"gtc",
                "client_order_id":"existing-paper-order",
                "notional":"5",
            },
        )
        journal.record_approved_draft(existing,at=NOW)
        journal.begin_submission(existing,at=NOW)
        self.assertTrue(journal.has_unresolved())
        with self.assertRaises(PermissionError):
            persist_crypto_paper_executor_draft(
                _dry_run(),
                journal=journal,
                at=NOW,
            )


if __name__=="__main__":
    unittest.main()

import hashlib
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from signal_vault.historical_bootstrap_paper_draft import (
    persist_bootstrap_crypto_paper_draft,
)
from signal_vault.historical_bootstrap_supervised_paper import (
    VALIDATION_KIND,
    build_supervised_bootstrap_paper_preview,
)
from signal_vault.multimarket_execution_journal import MultiMarketExecutionJournal


NOW=datetime(2026,10,1,19,0,tzinfo=timezone.utc)
STRATEGY="generic-ema12x26-v1-predeclared"


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
        "latest_newly_observed_UTC_close":"2026-10-01T18:00:00+00:00",
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


class HistoricalBootstrapPaperDraftTests(unittest.TestCase):
    def make_journal(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        journal=MultiMarketExecutionJournal(Path(temp.name)/"execution.sqlite3")
        self.addCleanup(journal.close)
        return journal

    def preview(self):
        return build_supervised_bootstrap_paper_preview(
            validation(),shadow(),account_state=account(),max_loss_usd="2"
        )

    def test_ready_bootstrap_preview_persists_durable_paper_draft_only(self):
        journal=self.make_journal()
        result=persist_bootstrap_crypto_paper_draft(
            self.preview(),journal=journal,at=NOW
        )
        self.assertEqual(result["status"],"DURABLE_CRYPTO_PAPER_DRAFT_APPROVED_NOT_SUBMITTED")
        self.assertEqual(result["source_mode"],"HISTORICAL_BOOTSTRAP_SUPERVISED_PAPER")
        self.assertFalse(result["independent_prospective_gate_passed"])
        self.assertTrue(result["paper_period_is_forward_validation"])
        self.assertEqual(result["instrument"],"BTC/USD")
        self.assertEqual(result["max_loss_usd"],"2")
        self.assertFalse(result["provider_post_attempted"])
        self.assertEqual(result["paper_order_submission"],"DISABLED")
        draft=journal.get_approved_draft(result["decision_id"])
        self.assertEqual(draft.instrument,"BTC/USD")
        self.assertEqual(str(draft.max_loss_usd),"2")

    def test_tampered_forward_gate_claim_is_rejected_before_write(self):
        journal=self.make_journal()
        raw=self.preview()
        raw["paper_preview"]["forward_gate_passed"]=True
        with self.assertRaises(ValueError):
            persist_bootstrap_crypto_paper_draft(raw,journal=journal,at=NOW)
        self.assertEqual(
            journal.connection.execute("SELECT COUNT(*) FROM mm_execution_drafts").fetchone()[0],
            0,
        )

    def test_unresolved_cross_market_order_blocks_new_bootstrap_draft(self):
        journal=self.make_journal()
        first=persist_bootstrap_crypto_paper_draft(
            self.preview(),journal=journal,at=NOW
        )
        draft=journal.get_approved_draft(first["decision_id"])
        journal.begin_submission(draft,at=NOW)
        with self.assertRaises(PermissionError):
            persist_bootstrap_crypto_paper_draft(
                self.preview(),journal=journal,at=NOW
            )


if __name__=="__main__":
    unittest.main()

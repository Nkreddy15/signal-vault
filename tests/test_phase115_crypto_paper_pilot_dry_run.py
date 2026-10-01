import unittest

from signal_vault.crypto_paper_activation_handoff import (
    AUTH_ENVIRONMENT,
    AUTH_KIND,
    AUTH_SCOPE,
)
from signal_vault.crypto_paper_pilot_dry_run import run_crypto_paper_pilot_dry_run
from signal_vault.crypto_paper_pilot_review import ENGINEERING_KIND


STRATEGY="generic-ema12x26-v1-predeclared"


def forward_review(*,complete=True,eligible=None):
    return {
        "kind":"PREDECLARED_SIX_CRYPTO_FORWARD_REVIEW_GATE_NOT_TRADING_AUTHORIZATION",
        "evidence_window_complete_for_gate":complete,
        "candidates_meeting_all_review_criteria":(
            [STRATEGY] if eligible is None else eligible
        ),
        "candidate_order_has_no_rank_or_preference":True,
        "automatic_candidate_selection":"DISABLED",
        "paper_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
        "separate_owner_authorization_still_required_for_any_PAPER_execution":True,
    }


def engineering(**overrides):
    raw={
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
    raw.update(overrides)
    return raw


def shadow(*,buys=("BTC/USD",)):
    symbols=("BTC/USD","ETH/USD","SOL/USD")
    signals={}
    for index,symbol in enumerate(symbols):
        signals[symbol]={
            STRATEGY:{
                "flat":{
                    "hypothetical_action":"buy" if symbol in buys else "hold",
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
        "latest_newly_observed_UTC_close":"2026-10-01T05:00:00+00:00",
        "shadow_payload_sha256":"c"*64,
        "predeclared_flat_and_held_hypothetical_decisions":signals,
        "broker_order_submission":"DISABLED",
        "automatic_paper_trading":"DISABLED",
        "live_trading":"UNAVAILABLE",
        "strategy_promoted":False,
        "future_edge_established":False,
    }


def account(**overrides):
    raw={
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
    raw.update(overrides)
    return raw


def owner(**overrides):
    raw={
        "kind":AUTH_KIND,
        "scope":AUTH_SCOPE,
        "environment":AUTH_ENVIRONMENT,
        "authorized":True,
        "max_single_order_loss_usd":"5",
        "live_trading_authorized":False,
    }
    raw.update(overrides)
    return raw


class CryptoPaperPilotDryRunTests(unittest.TestCase):
    def test_complete_pipeline_reaches_executor_review_without_execution(self):
        result=run_crypto_paper_pilot_dry_run(
            forward_review=forward_review(),
            engineering_evidence=engineering(),
            latest_shadow=shadow(),
            account_state=account(),
            owner_authorization=owner(),
            max_loss_usd="5",
        )
        self.assertEqual(
            result["status"],
            "READY_FOR_SEPARATE_PAPER_EXECUTOR_INVOCATION_REVIEW",
        )
        self.assertTrue(
            result["eligible_for_separate_paper_executor_invocation_review"]
        )
        self.assertEqual(
            result["decision_builder"]["decision_intent"]["instrument"],
            "BTC/USD",
        )
        self.assertEqual(
            result["paper_preview"]["route"]["environment"],
            "paper",
        )
        self.assertFalse(result["execution_journal_opened"])
        self.assertEqual(result["network_requests"],"NONE")
        self.assertFalse(result["provider_post_attempted"])
        self.assertFalse(result["paper_executor_invoked"])
        self.assertEqual(result["paper_order_submission"],"DISABLED")
        self.assertEqual(result["live_trading"],"UNAVAILABLE")

    def test_incomplete_forward_review_stops_before_decision(self):
        result=run_crypto_paper_pilot_dry_run(
            forward_review=forward_review(complete=False,eligible=[]),
            engineering_evidence=engineering(),
            latest_shadow=shadow(),
            account_state=account(),
            owner_authorization=owner(),
        )
        self.assertEqual(
            result["status"],
            "BLOCKED_FROZEN_PAPER_REVIEW_INCOMPLETE",
        )
        self.assertIsNone(result["decision_builder"])
        self.assertIsNone(result["paper_preview"])
        self.assertIsNone(result["activation_handoff"])

    def test_multiple_buys_stop_without_asset_ranking(self):
        result=run_crypto_paper_pilot_dry_run(
            forward_review=forward_review(),
            engineering_evidence=engineering(),
            latest_shadow=shadow(buys=("BTC/USD","ETH/USD")),
            account_state=account(),
            owner_authorization=owner(),
        )
        self.assertEqual(
            result["status"],
            "BLOCKED_MULTIPLE_SIMULTANEOUS_BUYS_NO_ASSET_RANKING",
        )
        self.assertIsNone(result["paper_preview"])
        self.assertIsNone(result["activation_handoff"])

    def test_risk_halt_stops_before_owner_handoff(self):
        result=run_crypto_paper_pilot_dry_run(
            forward_review=forward_review(),
            engineering_evidence=engineering(),
            latest_shadow=shadow(),
            account_state=account(operator_halted=True),
            owner_authorization=owner(),
        )
        self.assertEqual(result["status"],"BLOCKED_SHARED_RISK_GOVERNOR")
        self.assertIn(
            "OPERATOR_HALTED",
            result["paper_preview"]["risk_assessment"]["rejection_reasons"],
        )
        self.assertIsNone(result["activation_handoff"])

    def test_owner_limit_stops_handoff_without_execution(self):
        result=run_crypto_paper_pilot_dry_run(
            forward_review=forward_review(),
            engineering_evidence=engineering(),
            latest_shadow=shadow(),
            account_state=account(),
            owner_authorization=owner(max_single_order_loss_usd="4"),
            max_loss_usd="5",
        )
        self.assertEqual(result["status"],"BLOCKED_OWNER_ACTIVATION_HANDOFF")
        self.assertFalse(
            result["eligible_for_separate_paper_executor_invocation_review"]
        )
        self.assertFalse(result["provider_post_attempted"])


if __name__=="__main__":
    unittest.main()

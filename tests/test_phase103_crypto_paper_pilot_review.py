import unittest

from signal_vault.crypto_paper_pilot_review import (
    ENGINEERING_KIND,
    assess_crypto_paper_pilot_review,
)


def forward(*,complete=False,eligible=None):
    return {
        "kind":"PREDECLARED_SIX_CRYPTO_FORWARD_REVIEW_GATE_NOT_TRADING_AUTHORIZATION",
        "evidence_window_complete_for_gate":complete,
        "candidates_meeting_all_review_criteria":eligible or [],
        "paper_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
        "separate_owner_authorization_still_required_for_any_PAPER_execution":True,
    }


def engineering(**overrides):
    raw={
        "kind":ENGINEERING_KIND,
        "environment":"alpaca_paper",
        "live_host_requests":0,
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


class CryptoPaperPilotReviewTests(unittest.TestCase):
    def test_incomplete_forward_gate_blocks_pilot_review(self):
        result=assess_crypto_paper_pilot_review(
            forward(complete=False,eligible=[]),
            engineering(),
        )
        self.assertFalse(
            result["eligible_for_separate_owner_paper_pilot_activation_review"]
        )
        self.assertIn(
            "frozen_forward_review_window_complete",
            result["failed_checks"],
        )
        self.assertEqual(result["paper_order_submission"],"DISABLED")

    def test_all_technical_evidence_only_opens_separate_owner_review(self):
        result=assess_crypto_paper_pilot_review(
            forward(
                complete=True,
                eligible=["generic-ema12x26-v1-predeclared"],
            ),
            engineering(),
        )
        self.assertTrue(
            result["eligible_for_separate_owner_paper_pilot_activation_review"]
        )
        self.assertEqual(result["failed_checks"],[])
        self.assertFalse(result["paper_pilot_activation_permitted"])
        self.assertFalse(result["owner_autonomous_paper_authorization_recorded"])
        self.assertEqual(result["automatic_paper_activation"],"DISABLED")
        self.assertEqual(result["paper_order_submission"],"DISABLED")
        self.assertEqual(result["live_trading"],"UNAVAILABLE")

    def test_any_execution_safety_failure_blocks_review(self):
        for field,value in (
            ("supervised_paper_smoke_reconciled",False),
            ("paper_host_only_verified",False),
            ("fresh_provider_preflight_passed",False),
            ("durable_commit_before_post_validated",False),
            ("duplicate_submission_prevention_validated",False),
            ("unknown_result_recovery_validated",False),
            ("provider_reconciliation_path_validated",False),
            ("shared_cross_market_risk_governor_validated",False),
            ("unresolved_paper_orders",1),
            ("operator_halted",True),
        ):
            with self.subTest(field=field):
                result=assess_crypto_paper_pilot_review(
                    forward(
                        complete=True,
                        eligible=["generic-momentum24bar50bps-v1-predeclared"],
                    ),
                    engineering(**{field:value}),
                )
                self.assertFalse(
                    result["eligible_for_separate_owner_paper_pilot_activation_review"]
                )
                self.assertFalse(result["paper_pilot_activation_permitted"])

    def test_live_or_malformed_engineering_receipt_is_rejected(self):
        bad=engineering()
        bad["live_host_requests"]=1
        with self.assertRaises(ValueError):
            assess_crypto_paper_pilot_review(
                forward(complete=True,eligible=["x"]),
                bad,
            )


if __name__=="__main__":
    unittest.main()

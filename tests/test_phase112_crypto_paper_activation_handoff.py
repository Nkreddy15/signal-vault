import unittest

from signal_vault.crypto_paper_activation_handoff import (
    AUTH_ENVIRONMENT,
    AUTH_KIND,
    AUTH_SCOPE,
    assess_crypto_paper_activation_handoff,
)
from signal_vault.crypto_paper_pilot_review import KIND as REVIEW_KIND
from signal_vault.paper_intent_preview import KIND as PREVIEW_KIND


def review():
    return {
        "kind":REVIEW_KIND,
        "eligible_for_separate_owner_paper_pilot_activation_review":True,
        "paper_pilot_activation_permitted":False,
        "paper_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


def preview():
    return {
        "kind":PREVIEW_KIND,
        "decision_id":"preview-crypto-001",
        "market_lane":"crypto",
        "instrument":"BTC/USD",
        "route_status":"VALIDATED_PREVIEW_NO_SUBMISSION",
        "route":{
            "market_lane":"crypto",
            "provider":"alpaca",
            "environment":"paper",
            "adapter":"alpaca_crypto_paper",
            "endpoint":"https://paper-api.alpaca.markets/v2/orders",
            "payload":{},
            "required_acknowledgement":"x",
            "live_trading_available":False,
            "automatic_submission":"DISABLED",
        },
        "risk_assessment":{
            "risk_admissible":True,
            "assessment_is_not_trading_authorization":True,
            "proposed_max_loss_usd":"5",
        },
        "network_requests":"NONE",
        "credentials_accessed":"NONE",
        "provider_post_attempted":False,
        "paper_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


def authorization(**overrides):
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


class CryptoPaperActivationHandoffTests(unittest.TestCase):
    def test_complete_paper_only_handoff_still_does_not_execute(self):
        result=assess_crypto_paper_activation_handoff(
            review(),preview(),authorization()
        )
        self.assertTrue(
            result["eligible_for_separate_paper_executor_invocation_review"]
        )
        self.assertFalse(result["executor_invocation_performed"])
        self.assertFalse(result["execution_journal_write_performed"])
        self.assertEqual(result["network_requests"],"NONE")
        self.assertFalse(result["provider_post_attempted"])
        self.assertEqual(result["paper_order_submission"],"DISABLED")
        self.assertEqual(result["live_trading"],"UNAVAILABLE")

    def test_owner_risk_limit_below_preview_blocks_handoff(self):
        result=assess_crypto_paper_activation_handoff(
            review(),preview(),authorization(max_single_order_loss_usd="4")
        )
        self.assertFalse(
            result["eligible_for_separate_paper_executor_invocation_review"]
        )
        self.assertIn(
            "owner_limit_covers_previewed_risk",
            result["failed_checks"],
        )

    def test_live_authorization_is_rejected_by_handoff(self):
        result=assess_crypto_paper_activation_handoff(
            review(),preview(),authorization(live_trading_authorized=True)
        )
        self.assertFalse(
            result["eligible_for_separate_paper_executor_invocation_review"]
        )
        self.assertIn("owner_did_not_authorize_live",result["failed_checks"])
        self.assertEqual(result["live_order_submission"],"DISABLED")

    def test_ineligible_review_or_nonpreview_route_fails_closed(self):
        bad_review=review()
        bad_review["eligible_for_separate_owner_paper_pilot_activation_review"]=False
        with self.assertRaises(ValueError):
            assess_crypto_paper_activation_handoff(
                bad_review,preview(),authorization()
            )

        bad_preview=preview()
        bad_preview["provider_post_attempted"]=True
        with self.assertRaises(ValueError):
            assess_crypto_paper_activation_handoff(
                review(),bad_preview,authorization()
            )


if __name__=="__main__":
    unittest.main()

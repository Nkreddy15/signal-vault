import unittest

from signal_vault.crypto_paper_decision_intent import build_crypto_entry_intent
from signal_vault.paper_intent_preview import DECISION_KIND


def review(eligible):
    return {
        "kind":"PREDECLARED_SIX_CRYPTO_FORWARD_REVIEW_GATE_NOT_TRADING_AUTHORIZATION",
        "evidence_window_complete_for_gate":True,
        "candidate_order_has_no_rank_or_preference":True,
        "automatic_candidate_selection":"DISABLED",
        "candidates_meeting_all_review_criteria":eligible,
        "paper_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


def shadow(actions):
    strategy="generic-ema12x26-v1-predeclared"
    signals={}
    for symbol,action in actions.items():
        signals[symbol]={
            strategy:{
                "flat":{
                    "hypothetical_action":action,
                    "evidence_sha256":(symbol.replace("/","")+"a"*64)[:64],
                },
                "already_held":{
                    "hypothetical_action":"hold",
                    "evidence_sha256":"b"*64,
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


class CryptoPaperDecisionIntentTests(unittest.TestCase):
    def test_exactly_one_buy_builds_deterministic_phase111_intent(self):
        s=shadow({
            "BTC/USD":"buy",
            "ETH/USD":"hold",
            "SOL/USD":"hold",
        })
        result=build_crypto_entry_intent(
            review(["generic-ema12x26-v1-predeclared"]),
            s,
            max_loss_usd="5",
        )
        self.assertEqual(
            result["status"],
            "ONE_UNAMBIGUOUS_PAPER_ENTRY_INTENT_PREVIEWABLE",
        )
        intent=result["decision_intent"]
        self.assertEqual(intent["kind"],DECISION_KIND)
        self.assertEqual(intent["market_lane"],"crypto")
        self.assertEqual(intent["instrument"],"BTC/USD")
        self.assertEqual(intent["provider_payload"]["notional"],"5")
        self.assertTrue(intent["forward_gate_passed"])
        self.assertTrue(intent["separate_owner_activation_required"])
        again=build_crypto_entry_intent(
            review(["generic-ema12x26-v1-predeclared"]),
            s,
            max_loss_usd="5",
        )
        self.assertEqual(
            again["decision_intent"]["decision_id"],
            intent["decision_id"],
        )
        self.assertEqual(result["network_requests"],"NONE")
        self.assertEqual(result["paper_order_submission"],"DISABLED")

    def test_multiple_strategies_are_never_ranked(self):
        result=build_crypto_entry_intent(
            review([
                "generic-ema12x26-v1-predeclared",
                "generic-momentum24bar50bps-v1-predeclared",
            ]),
            shadow({"BTC/USD":"buy"}),
        )
        self.assertEqual(
            result["status"],
            "BLOCKED_MULTIPLE_ELIGIBLE_STRATEGIES_NO_RANKING",
        )
        self.assertIsNone(result["decision_intent"])

    def test_multiple_simultaneous_buys_are_never_asset_ranked(self):
        result=build_crypto_entry_intent(
            review(["generic-ema12x26-v1-predeclared"]),
            shadow({"BTC/USD":"buy","ETH/USD":"buy","SOL/USD":"hold"}),
        )
        self.assertEqual(
            result["status"],
            "BLOCKED_MULTIPLE_SIMULTANEOUS_BUYS_NO_ASSET_RANKING",
        )
        self.assertIsNone(result["decision_intent"])
        self.assertEqual(
            result["buy_signal_symbols"],
            ["BTC/USD","ETH/USD"],
        )

    def test_no_buy_or_no_eligible_strategy_holds(self):
        result=build_crypto_entry_intent(
            review(["generic-ema12x26-v1-predeclared"]),
            shadow({"BTC/USD":"hold","ETH/USD":"hold"}),
        )
        self.assertEqual(result["status"],"HOLD_NO_CURRENT_UNAMBIGUOUS_BUY")
        self.assertIsNone(result["decision_intent"])

        result=build_crypto_entry_intent(
            review([]),
            shadow({"BTC/USD":"buy"}),
        )
        self.assertEqual(result["status"],"HOLD_NO_ELIGIBLE_FORWARD_STRATEGY")
        self.assertIsNone(result["decision_intent"])

    def test_notional_is_tightly_bounded(self):
        with self.assertRaises(ValueError):
            build_crypto_entry_intent(
                review(["generic-ema12x26-v1-predeclared"]),
                shadow({"BTC/USD":"buy"}),
                max_loss_usd="11",
            )


if __name__=="__main__":
    unittest.main()

import unittest

from signal_vault.paper_intent_preview import (
    DECISION_KIND,
    KIND,
    preview_paper_intent,
)


ACCOUNT={
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


def crypto_decision():
    return {
        "kind":DECISION_KIND,
        "decision_id":"preview-crypto-001",
        "market_lane":"crypto",
        "instrument":"BTC/USD",
        "max_loss_usd":"5",
        "provider_payload":{
            "symbol":"BTC/USD",
            "side":"buy",
            "type":"market",
            "time_in_force":"gtc",
            "client_order_id":"preview-crypto-001",
            "notional":"5",
        },
        "strategy_evidence_sha256":"a"*64,
        "forward_gate_passed":False,
        "separate_owner_activation_required":True,
    }


class PaperIntentPreviewTests(unittest.TestCase):
    def test_crypto_preview_routes_without_submission(self):
        result=preview_paper_intent(crypto_decision(),account_state=ACCOUNT)
        self.assertEqual(result["kind"],KIND)
        self.assertTrue(result["risk_assessment"]["risk_admissible"])
        self.assertEqual(result["route_status"],"VALIDATED_PREVIEW_NO_SUBMISSION")
        self.assertEqual(result["route"]["provider"],"alpaca")
        self.assertEqual(result["route"]["environment"],"paper")
        self.assertEqual(result["network_requests"],"NONE")
        self.assertEqual(result["credentials_accessed"],"NONE")
        self.assertFalse(result["provider_post_attempted"])
        self.assertEqual(result["durable_execution_journal_write"],"NONE")
        self.assertEqual(result["paper_order_submission"],"DISABLED")
        self.assertEqual(result["live_trading"],"UNAVAILABLE")

    def test_risk_rejection_produces_no_route(self):
        account=dict(ACCOUNT)
        account["operator_halted"]=True
        result=preview_paper_intent(crypto_decision(),account_state=account)
        self.assertFalse(result["risk_assessment"]["risk_admissible"])
        self.assertIn("OPERATOR_HALTED",result["risk_assessment"]["rejection_reasons"])
        self.assertEqual(result["route_status"],"NOT_ROUTED_RISK_REJECTED")
        self.assertIsNone(result["route"])
        self.assertFalse(result["provider_post_attempted"])

    def test_equity_preview_uses_alpaca_paper_only(self):
        decision={
            "kind":DECISION_KIND,
            "decision_id":"preview-equity-001",
            "market_lane":"us_equity",
            "instrument":"SPY",
            "max_loss_usd":"5",
            "provider_payload":{
                "symbol":"SPY",
                "side":"buy",
                "type":"market",
                "time_in_force":"day",
                "client_order_id":"preview-equity-001",
                "notional":"5",
            },
            "strategy_evidence_sha256":"b"*64,
            "forward_gate_passed":False,
            "separate_owner_activation_required":True,
        }
        result=preview_paper_intent(decision,account_state=ACCOUNT)
        self.assertEqual(result["route"]["provider"],"alpaca")
        self.assertEqual(result["route"]["adapter"],"alpaca_equity_paper")
        self.assertFalse(result["route"]["live_trading_available"])

    def test_kalshi_preview_uses_demo_only(self):
        decision={
            "kind":DECISION_KIND,
            "decision_id":"preview-kalshi-001",
            "market_lane":"kalshi_event_contract",
            "instrument":"TEST-EVENT",
            "max_loss_usd":"5",
            "provider_payload":{
                "ticker":"TEST-EVENT",
                "side":"bid",
                "count":"5",
                "price":"0.40",
                "time_in_force":"good_till_canceled",
                "self_trade_prevention_type":"taker_at_cross",
                "client_order_id":"preview-kalshi-001",
            },
            "strategy_evidence_sha256":"c"*64,
            "forward_gate_passed":False,
            "separate_owner_activation_required":True,
        }
        result=preview_paper_intent(decision,account_state=ACCOUNT)
        self.assertEqual(result["route"]["provider"],"kalshi")
        self.assertEqual(result["route"]["environment"],"demo")
        self.assertEqual(result["demo_order_submission"],"DISABLED")

    def test_extra_fields_or_missing_owner_gate_fail_closed(self):
        decision=crypto_decision()
        decision["unexpected"]="nope"
        with self.assertRaises(ValueError):
            preview_paper_intent(decision,account_state=ACCOUNT)

        decision=crypto_decision()
        decision["separate_owner_activation_required"]=False
        with self.assertRaises(ValueError):
            preview_paper_intent(decision,account_state=ACCOUNT)


if __name__=="__main__":
    unittest.main()

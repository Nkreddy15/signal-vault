import hashlib
import unittest

from signal_vault.historical_bootstrap_supervised_paper import (
    VALIDATION_KIND,
    assess_historical_bootstrap_validation,
    build_supervised_bootstrap_paper_preview,
)


STRATEGY="generic-ema12x26-v1-predeclared"


def validation():
    raw={
        "kind":VALIDATION_KIND,
        "symbols":["AVAX/USD","BTC/USD","ETH/USD","LINK/USD","LTC/USD","SOL/USD"],
        "historical_hours":144,
        "chronological_fold_count":4,
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
    payload=repr(sorted(raw.items())).encode()
    raw["receipt_sha256"]=hashlib.sha256(payload).hexdigest()
    return raw


def shadow(*,buy_symbol="BTC/USD"):
    symbols=["AVAX/USD","BTC/USD","ETH/USD","LINK/USD","LTC/USD","SOL/USD"]
    decisions={}
    for s in symbols:
        action="buy" if s==buy_symbol else "hold"
        decisions[s]={
            STRATEGY:{
                "flat":{
                    "hypothetical_action":action,
                    "evidence_sha256":hashlib.sha256((s+action).encode()).hexdigest(),
                }
            }
        }
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


class HistoricalBootstrapSupervisedPaperTests(unittest.TestCase):
    def test_clean_history_is_eligible_for_supervised_paper_only(self):
        result=assess_historical_bootstrap_validation(validation())
        self.assertTrue(result["eligible_for_supervised_paper_bootstrap"])
        self.assertFalse(result["independent_prospective_gate_passed"])
        self.assertEqual(result["automatic_paper_activation"],"DISABLED")
        self.assertEqual(result["live_trading"],"UNAVAILABLE")

    def test_historical_data_is_never_reclassified_as_prospective(self):
        bad=validation()
        bad["historical_data_is_not_prospective_validation"]=False
        result=assess_historical_bootstrap_validation(bad)
        self.assertFalse(result["eligible_for_supervised_paper_bootstrap"])
        self.assertIn("historical_not_labeled_prospective",result["failed_checks"])

    def test_current_prospective_btc_signal_can_create_tiny_paper_preview(self):
        result=build_supervised_bootstrap_paper_preview(
            validation(),shadow(),account_state=account(),max_loss_usd="2"
        )
        self.assertEqual(result["status"],"READY_FOR_SUPERVISED_PAPER_DRAFT_REVIEW")
        self.assertEqual(result["paper_preview"]["instrument"],"BTC/USD")
        self.assertFalse(result["paper_preview"]["forward_gate_passed"])
        self.assertTrue(result["paper_period_is_forward_validation"])
        self.assertFalse(result["live_promotion_permitted"])
        self.assertFalse(result["provider_post_attempted"])
        self.assertEqual(result["paper_order_submission"],"DISABLED")

    def test_non_btc_buy_holds_until_executor_is_hardened_for_symbol(self):
        result=build_supervised_bootstrap_paper_preview(
            validation(),shadow(buy_symbol="ETH/USD"),account_state=account()
        )
        self.assertEqual(
            result["status"],
            "HOLD_CURRENT_BUY_NOT_YET_SUPPORTED_BY_FIRST_BTC_ONLY_EXECUTOR",
        )
        self.assertIsNone(result["paper_preview"])

    def test_notional_over_five_is_rejected(self):
        with self.assertRaises(ValueError):
            build_supervised_bootstrap_paper_preview(
                validation(),shadow(),account_state=account(),max_loss_usd="6"
            )


if __name__=="__main__":
    unittest.main()

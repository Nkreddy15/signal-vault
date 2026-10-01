import unittest

from signal_vault.kalshi_demo_execution_acceptance import (
    POLICY_VERSION,
    assess_kalshi_demo_execution,
)


def summary():
    return {
        "kind":"KALSHI_DEMO_EXECUTION_VALIDATION_SUMMARY",
        "environment":"demo",
        "demo_host_only_verified":True,
        "demo_order_count":20,
        "distinct_market_count":10,
        "provider_reconciled_order_count":20,
        "unresolved_order_count":0,
        "duplicate_client_order_id_count":0,
        "blind_retry_count":0,
        "post_without_durable_submission_pending_count":0,
        "shared_risk_governor_bypass_count":0,
        "restart_recovery_case_count":1,
        "unknown_result_recovery_case_count":1,
        "live_host_requests":0,
        "live_order_submission":"DISABLED",
    }


class KalshiDemoExecutionAcceptanceTests(unittest.TestCase):
    def test_execution_mechanics_can_pass_without_enabling_live_trading(self):
        result=assess_kalshi_demo_execution(summary())
        self.assertEqual(result["policy_version"],POLICY_VERSION)
        self.assertTrue(result["demo_execution_validated"])
        self.assertTrue(
            result["restart_and_unknown_result_recovery_validated"]
        )
        self.assertTrue(result["provider_reconciliation_validated"])
        self.assertFalse(
            result["strategy_profitability_used_for_execution_acceptance"]
        )
        self.assertFalse(
            result["historical_pnl_used_for_execution_acceptance"]
        )
        self.assertFalse(result["live_credentials_configured"])
        self.assertFalse(result["owner_live_authorization_recorded"])
        self.assertEqual(result["live_order_submission"],"DISABLED")
        self.assertEqual(
            result["next_action"],
            "CONTINUE_SEPARATE_PROSPECTIVE_STRATEGY_VALIDATION",
        )

    def test_any_duplicate_retry_unresolved_or_risk_bypass_fails(self):
        for key in (
            "unresolved_order_count",
            "duplicate_client_order_id_count",
            "blind_retry_count",
            "post_without_durable_submission_pending_count",
            "shared_risk_governor_bypass_count",
        ):
            item=summary()
            item[key]=1
            with self.subTest(key=key):
                result=assess_kalshi_demo_execution(item)
                self.assertFalse(result["demo_execution_validated"])
                self.assertEqual(
                    result["next_action"],
                    "DEMO_EXECUTION_VALIDATION_INCOMPLETE",
                )

    def test_missing_recovery_or_reconciliation_or_activity_fails(self):
        cases=(
            ("distinct_market_count",9),
            ("provider_reconciled_order_count",19),
            ("restart_recovery_case_count",0),
            ("unknown_result_recovery_case_count",0),
        )
        for key,value in cases:
            item=summary()
            item[key]=value
            with self.subTest(key=key):
                self.assertFalse(
                    assess_kalshi_demo_execution(item)[
                        "demo_execution_validated"
                    ]
                )

        # Keep reconciliation structurally consistent when reducing activity.
        item=summary()
        item["demo_order_count"]=19
        item["provider_reconciled_order_count"]=19
        self.assertFalse(
            assess_kalshi_demo_execution(item)["demo_execution_validated"]
        )

    def test_non_demo_or_live_host_activity_is_rejected(self):
        item=summary()
        item["environment"]="production"
        with self.assertRaises(ValueError):
            assess_kalshi_demo_execution(item)

        item=summary()
        item["live_host_requests"]=1
        with self.assertRaises(ValueError):
            assess_kalshi_demo_execution(item)


if __name__=="__main__":
    unittest.main()

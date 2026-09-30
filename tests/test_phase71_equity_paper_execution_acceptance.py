import unittest

from signal_vault.equity_paper_execution_acceptance import (
    POLICY_VERSION,
    assess_equity_paper_execution,
)


def summary():
    return {
        "kind":"EQUITY_PAPER_EXECUTION_VALIDATION_SUMMARY",
        "environment":"alpaca_paper",
        "paper_host_only_verified":True,
        "paper_order_count":20,
        "distinct_symbol_count":4,
        "provider_rule_preflight_pass_count":20,
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


class EquityPaperExecutionAcceptanceTests(unittest.TestCase):
    def test_execution_can_pass_without_live_activation_or_profit_assumption(self):
        result=assess_equity_paper_execution(summary())
        self.assertEqual(result["policy_version"],POLICY_VERSION)
        self.assertTrue(result["paper_execution_validated"])
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

    def test_any_reconciliation_retry_commit_or_risk_failure_blocks_acceptance(self):
        for key in (
            "provider_reconciled_order_count",
            "provider_rule_preflight_pass_count",
            "unresolved_order_count",
            "duplicate_client_order_id_count",
            "blind_retry_count",
            "post_without_durable_submission_pending_count",
            "shared_risk_governor_bypass_count",
        ):
            item=summary()
            item[key]=19 if key in (
                "provider_reconciled_order_count",
                "provider_rule_preflight_pass_count",
            ) else 1
            with self.subTest(key=key):
                self.assertFalse(
                    assess_equity_paper_execution(item)[
                        "paper_execution_validated"
                    ]
                )

    def test_insufficient_activity_or_recovery_fails(self):
        cases=(
            ("paper_order_count",19),
            ("distinct_symbol_count",3),
            ("restart_recovery_case_count",0),
            ("unknown_result_recovery_case_count",0),
        )
        for key,value in cases:
            item=summary()
            if key=="paper_order_count":
                item["provider_rule_preflight_pass_count"]=19
                item["provider_reconciled_order_count"]=19
            item[key]=value
            with self.subTest(key=key):
                self.assertFalse(
                    assess_equity_paper_execution(item)[
                        "paper_execution_validated"
                    ]
                )

    def test_non_paper_or_live_host_activity_is_rejected(self):
        item=summary()
        item["environment"]="live"
        with self.assertRaises(ValueError):
            assess_equity_paper_execution(item)

        item=summary()
        item["live_host_requests"]=1
        with self.assertRaises(ValueError):
            assess_equity_paper_execution(item)


if __name__=="__main__":
    unittest.main()

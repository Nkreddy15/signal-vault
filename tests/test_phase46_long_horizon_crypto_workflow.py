import unittest

from signal_vault.ci_historical_crypto import resolve_manual_ci_configuration


class LongHorizonCryptoWorkflowTests(unittest.TestCase):
    def test_six_crypto_420_day_plan_is_exactly_30_bounded_windows(self):
        env={
            "GITHUB_ACTIONS":"true",
            "GITHUB_EVENT_NAME":"workflow_dispatch",
            "GITHUB_REPOSITORY":"Nkreddy15/signal-vault",
            "GITHUB_REF":"refs/heads/main",
            "SIGNAL_VAULT_RESEARCH_READ_APPROVED":"HISTORICAL_CRYPTO_DATA_GET_ONLY",
            "SIGNAL_VAULT_RESEARCH_SYMBOLS":
                "BTC/USD ETH/USD SOL/USD LTC/USD LINK/USD AVAX/USD",
            "SIGNAL_VAULT_RESEARCH_START_UTC":"2025-08-01T00:00:00Z",
            "SIGNAL_VAULT_RESEARCH_END_UTC":"2026-09-25T00:00:00Z",
        }
        result=resolve_manual_ci_configuration(env=env)
        plan=result["plan"]
        self.assertEqual(plan["window_count"],30)
        self.assertEqual(plan["requests_triggered"],0)
        self.assertEqual(plan["credential_access"],"NONE")
        self.assertEqual(plan["broker_order_submission"],"DISABLED")
        self.assertEqual(
            plan["symbols"],
            ["BTC/USD","ETH/USD","SOL/USD","LTC/USD","LINK/USD","AVAX/USD"],
        )

    def test_more_than_420_days_is_rejected_before_any_credentials(self):
        env={
            "GITHUB_ACTIONS":"true",
            "GITHUB_EVENT_NAME":"workflow_dispatch",
            "GITHUB_REPOSITORY":"Nkreddy15/signal-vault",
            "GITHUB_REF":"refs/heads/main",
            "SIGNAL_VAULT_RESEARCH_READ_APPROVED":"HISTORICAL_CRYPTO_DATA_GET_ONLY",
            "SIGNAL_VAULT_RESEARCH_SYMBOLS":"BTC/USD ETH/USD",
            "SIGNAL_VAULT_RESEARCH_START_UTC":"2025-07-31T00:00:00Z",
            "SIGNAL_VAULT_RESEARCH_END_UTC":"2026-09-25T00:00:00Z",
        }
        with self.assertRaises(ValueError):
            resolve_manual_ci_configuration(env=env)


if __name__=="__main__":
    unittest.main()

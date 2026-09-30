import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from signal_vault.all_market_activation_preflight import (
    EXPECTED_CRON,
    EXPECTED_START_COMMAND,
    all_market_activation_preflight,
)
from signal_vault.equity_cloud_sidecar import (
    ACTIVATION as EQUITY_VALUE,
    ACTIVATION_ENV as EQUITY_ENV,
)
from signal_vault.kalshi_cloud_sidecar import (
    ACTIVATION_ENV as KALSHI_ENV,
    ACTIVATION_VALUE as KALSHI_VALUE,
)
from signal_vault.railway_btc_first_dual_cron import (
    ACTIVATION_FLAG as CRYPTO_ENV,
    ACTIVATION_VALUE as CRYPTO_VALUE,
)


class AllMarketActivationPreflightTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)/"forward"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        self.env={
            CRYPTO_ENV:CRYPTO_VALUE,
            EQUITY_ENV:EQUITY_VALUE,
            KALSHI_ENV:KALSHI_VALUE,
        }

    def test_exact_flags_start_command_cron_and_root_are_required(self):
        with patch(
            "signal_vault.all_market_activation_preflight.CLOUD_ROOT",
            self.root,
        ):
            result=all_market_activation_preflight(
                environ=self.env,
                root=self.root,
                observed_start_command=EXPECTED_START_COMMAND,
                observed_cron_schedule=EXPECTED_CRON,
            )
        self.assertTrue(result["shared_forward_root_matches_expected"])
        self.assertTrue(result["all_three_research_lanes_explicitly_activated"])
        self.assertTrue(result["ready_for_existing_service_all_market_cron"])
        self.assertEqual(
            set(result["active_research_lanes"]),
            {"six_crypto","us_equity","kalshi"},
        )
        self.assertEqual(result["missing_or_unrecognized_activation_envs"],[])
        self.assertFalse(result["new_Railway_service_required"])
        self.assertFalse(result["new_Railway_volume_required"])
        self.assertFalse(result["new_paid_resource_required"])
        self.assertEqual(result["network_requests"],"NONE")
        self.assertEqual(result["credential_access"],"NONE")
        self.assertEqual(result["paper_order_submission"],"DISABLED")
        self.assertEqual(result["demo_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")

    def test_missing_or_unrecognized_flag_blocks_readiness(self):
        broken=dict(self.env)
        broken[KALSHI_ENV]="WRONG"
        with patch(
            "signal_vault.all_market_activation_preflight.CLOUD_ROOT",
            self.root,
        ):
            result=all_market_activation_preflight(
                environ=broken,
                root=self.root,
                observed_start_command=EXPECTED_START_COMMAND,
                observed_cron_schedule=EXPECTED_CRON,
            )
        self.assertFalse(result["ready_for_existing_service_all_market_cron"])
        self.assertFalse(result["activation_flags"]["kalshi"])
        self.assertIn(
            KALSHI_ENV,
            result["missing_or_unrecognized_activation_envs"],
        )

    def test_wrong_start_command_or_cron_blocks_readiness(self):
        with patch(
            "signal_vault.all_market_activation_preflight.CLOUD_ROOT",
            self.root,
        ):
            wrong_start=all_market_activation_preflight(
                environ=self.env,
                root=self.root,
                observed_start_command="python -m signal_vault.railway_forward_cron --once",
                observed_cron_schedule=EXPECTED_CRON,
            )
            wrong_cron=all_market_activation_preflight(
                environ=self.env,
                root=self.root,
                observed_start_command=EXPECTED_START_COMMAND,
                observed_cron_schedule="0 * * * *",
            )
        self.assertFalse(wrong_start["ready_for_existing_service_all_market_cron"])
        self.assertFalse(wrong_start["start_command_exact"])
        self.assertFalse(wrong_cron["ready_for_existing_service_all_market_cron"])
        self.assertFalse(wrong_cron["cron_schedule_exact"])

    def test_wrong_volume_path_blocks_readiness_even_with_all_flags(self):
        expected=self.root/"expected"
        expected.mkdir(mode=0o700)
        expected.chmod(0o700)
        with patch(
            "signal_vault.all_market_activation_preflight.CLOUD_ROOT",
            expected,
        ):
            result=all_market_activation_preflight(
                environ=self.env,
                root=self.root,
                observed_start_command=EXPECTED_START_COMMAND,
                observed_cron_schedule=EXPECTED_CRON,
            )
        self.assertFalse(result["shared_forward_root_matches_expected"])
        self.assertFalse(result["ready_for_existing_service_all_market_cron"])

    def test_start_and_cron_can_be_unobserved_for_code_only_preflight_but_root_and_flags_still_matter(self):
        with patch(
            "signal_vault.all_market_activation_preflight.CLOUD_ROOT",
            self.root,
        ):
            result=all_market_activation_preflight(
                environ=self.env,
                root=self.root,
            )
        self.assertIsNone(result["start_command_exact"])
        self.assertIsNone(result["cron_schedule_exact"])
        self.assertTrue(result["ready_for_existing_service_all_market_cron"])


if __name__=="__main__":
    unittest.main()

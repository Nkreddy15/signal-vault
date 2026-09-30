import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from signal_vault.railway_all_markets_research_cron import (
    combined_all_markets_once,
)


UTC=timezone.utc


class PostTickReadinessSnapshotTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)/"forward"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        self.btc=self.root/"observations.sqlite3"
        self.btc.write_bytes(b"original-btc")
        self.btc.chmod(0o600)

    @staticmethod
    def healthy_core(**kwargs):
        return {
            "crypto_btc_status":"SAFE_NO_NEW_OBSERVATION",
            "equity_status":"NO_DUE_CORE_HOUR",
            "btc_evidence_changed_during_equity_stage":False,
        }

    @staticmethod
    def inactive_kalshi(**kwargs):
        return {
            "status":"INACTIVE",
            "credentials_accessed":"NONE",
            "demo_order_submission":"DISABLED",
            "live_order_submission":"DISABLED",
        }

    def test_unchanged_btc_attaches_network_free_readiness_snapshot(self):
        readiness={
            "kind":"ALL_MARKET_FORWARD_READINESS_STATUS_NO_ORDERS",
            "network_requests":"NONE",
            "credential_access":"NONE",
            "broker_order_submission":"DISABLED",
            "paper_order_submission":"DISABLED",
            "demo_order_submission":"DISABLED",
            "live_order_submission":"DISABLED",
        }
        with patch(
            "signal_vault.railway_all_markets_research_cron.all_market_forward_status",
            return_value=readiness,
        ) as status_call:
            result=combined_all_markets_once(
                now=datetime(2026,9,30,22,7,tzinfo=UTC),
                environ={},
                btc_root=self.root,
                core_runner=self.healthy_core,
                kalshi_runner=self.inactive_kalshi,
            )
        status_call.assert_called_once_with(environ={},root=self.root)
        self.assertEqual(result["post_tick_readiness_status"],"AVAILABLE")
        self.assertEqual(
            result["post_tick_readiness"]["network_requests"],
            "NONE",
        )
        self.assertEqual(
            result["post_tick_readiness"]["credential_access"],
            "NONE",
        )
        self.assertEqual(result["paper_order_submission"],"DISABLED")
        self.assertEqual(result["demo_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")

    def test_readiness_failure_is_isolated_from_completed_market_tick(self):
        with patch(
            "signal_vault.railway_all_markets_research_cron.all_market_forward_status",
            side_effect=ValueError("fixture audit failure"),
        ):
            result=combined_all_markets_once(
                now=datetime(2026,9,30,22,7,tzinfo=UTC),
                environ={},
                btc_root=self.root,
                core_runner=self.healthy_core,
                kalshi_runner=self.inactive_kalshi,
            )
        self.assertEqual(result["kalshi_status"],"INACTIVE")
        self.assertEqual(result["post_tick_readiness_status"],"FAILED_SAFE")
        self.assertEqual(
            result["post_tick_readiness_failure_class"],
            "ValueError",
        )
        self.assertTrue(result["original_BTC_status_preserved"])

    def test_btc_mutation_guard_skips_readiness_snapshot(self):
        def mutating_kalshi(*,env,now):
            self.btc.write_bytes(b"mutated")
            self.btc.chmod(0o600)
            return {"status":"COLLECTION_TICK_COMPLETE"}

        with patch(
            "signal_vault.railway_all_markets_research_cron.all_market_forward_status",
            side_effect=AssertionError("readiness must not run after BTC mutation"),
        ) as status_call:
            result=combined_all_markets_once(
                now=datetime(2026,9,30,22,7,tzinfo=UTC),
                environ={},
                btc_root=self.root,
                core_runner=self.healthy_core,
                kalshi_runner=mutating_kalshi,
            )
        status_call.assert_not_called()
        self.assertEqual(
            result["kalshi_status"],
            "FAILED_BTC_EVIDENCE_MUTATION_GUARD",
        )
        self.assertEqual(
            result["post_tick_readiness_status"],
            "SKIPPED_BTC_INTEGRITY_NOT_PROVEN",
        )
        self.assertFalse(result["original_BTC_status_preserved"])


if __name__=="__main__":
    unittest.main()

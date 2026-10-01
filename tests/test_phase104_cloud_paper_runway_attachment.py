import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from signal_vault.railway_all_markets_research_cron import (
    combined_all_markets_once,
)


UTC=timezone.utc


class CloudPaperRunwayAttachmentTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)/"forward"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        btc=self.root/"observations.sqlite3"
        btc.write_bytes(b"original-btc")
        btc.chmod(0o600)

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

    def test_healthy_tick_attaches_read_only_paper_runway(self):
        readiness={
            "kind":"ALL_MARKET_FORWARD_READINESS_STATUS_NO_ORDERS",
            "broker_order_submission":"DISABLED",
            "paper_order_submission":"DISABLED",
            "demo_order_submission":"DISABLED",
            "live_order_submission":"DISABLED",
            "automatic_live_trading":"DISABLED",
            "live_trading":"UNAVAILABLE",
        }
        runway={
            "kind":"PAPER_RUNWAY_STATUS_NOT_ORDER_AUTHORIZATION",
            "current_forward_evidence_blockers":["SIX_CRYPTO_GATE"],
            "paper_order_submission":"DISABLED",
            "demo_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
            "network_requests":"NONE",
            "credential_access":"NONE",
        }
        with patch(
            "signal_vault.railway_all_markets_research_cron.all_market_forward_status",
            return_value=readiness,
        ), patch(
            "signal_vault.railway_all_markets_research_cron.paper_runway_from_forward_status",
            return_value=runway,
        ) as runway_call:
            result=combined_all_markets_once(
                now=datetime(2026,10,1,0,7,tzinfo=UTC),
                environ={},
                btc_root=self.root,
                core_runner=self.healthy_core,
                kalshi_runner=self.inactive_kalshi,
            )
        runway_call.assert_called_once_with(readiness)
        self.assertEqual(result["paper_runway_status"],"AVAILABLE")
        self.assertEqual(
            result["paper_runway"]["network_requests"],
            "NONE",
        )
        self.assertEqual(result["paper_order_submission"],"DISABLED")
        self.assertEqual(result["demo_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")
        self.assertTrue(result["original_BTC_status_preserved"])

    def test_runway_summary_failure_never_invalidates_completed_collection_tick(self):
        readiness={
            "kind":"ALL_MARKET_FORWARD_READINESS_STATUS_NO_ORDERS",
            "broker_order_submission":"DISABLED",
            "paper_order_submission":"DISABLED",
            "demo_order_submission":"DISABLED",
            "live_order_submission":"DISABLED",
            "automatic_live_trading":"DISABLED",
            "live_trading":"UNAVAILABLE",
        }
        with patch(
            "signal_vault.railway_all_markets_research_cron.all_market_forward_status",
            return_value=readiness,
        ), patch(
            "signal_vault.railway_all_markets_research_cron.paper_runway_from_forward_status",
            side_effect=ValueError("fixture"),
        ):
            result=combined_all_markets_once(
                now=datetime(2026,10,1,0,7,tzinfo=UTC),
                environ={},
                btc_root=self.root,
                core_runner=self.healthy_core,
                kalshi_runner=self.inactive_kalshi,
            )
        self.assertEqual(result["post_tick_readiness_status"],"AVAILABLE")
        self.assertEqual(result["paper_runway_status"],"FAILED_SAFE")
        self.assertEqual(result["paper_runway_failure_class"],"ValueError")
        self.assertTrue(result["original_BTC_status_preserved"])
        self.assertEqual(result["paper_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")


if __name__=="__main__":
    unittest.main()

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from signal_vault.railway_all_markets_research_cron import main


class RailwayAllMarketsStatusModeTests(unittest.TestCase):
    def test_status_mode_never_calls_collection_path(self):
        status={
            "kind":"ALL_MARKET_FORWARD_READINESS_STATUS_NO_ORDERS",
            "network_requests":"NONE",
            "credential_access":"NONE",
            "broker_order_submission":"DISABLED",
            "paper_order_submission":"DISABLED",
            "demo_order_submission":"DISABLED",
            "live_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        }
        output=io.StringIO()
        with patch(
            "signal_vault.railway_all_markets_research_cron.all_market_forward_status",
            return_value=status,
        ) as status_call, patch(
            "signal_vault.railway_all_markets_research_cron.combined_all_markets_once",
            side_effect=AssertionError("collection path must not run in --status"),
        ) as collect_call, redirect_stdout(output):
            code=main(["--status"])
        self.assertEqual(code,0)
        status_call.assert_called_once_with()
        collect_call.assert_not_called()
        body=json.loads(output.getvalue())
        self.assertEqual(body["network_requests"],"NONE")
        self.assertEqual(body["credential_access"],"NONE")
        self.assertEqual(body["broker_order_submission"],"DISABLED")
        self.assertEqual(body["paper_order_submission"],"DISABLED")
        self.assertEqual(body["demo_order_submission"],"DISABLED")
        self.assertEqual(body["live_order_submission"],"DISABLED")

    def test_once_mode_uses_guarded_collection_path_not_status(self):
        result={
            "kind":"RAILWAY_EXISTING_VOLUME_ALL_MARKETS_GET_ONLY_CRON",
            "core_status":"SAFE_NO_NEW_OBSERVATION",
            "kalshi_status":"INACTIVE",
            "broker_order_submission":"DISABLED",
            "paper_order_submission":"DISABLED",
            "demo_order_submission":"DISABLED",
            "live_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        }
        output=io.StringIO()
        with patch(
            "signal_vault.railway_all_markets_research_cron.combined_all_markets_once",
            return_value=result,
        ) as collect_call, patch(
            "signal_vault.railway_all_markets_research_cron.all_market_forward_status",
            side_effect=AssertionError("status path must not run in --once"),
        ) as status_call, redirect_stdout(output):
            code=main(["--once"])
        self.assertEqual(code,0)
        collect_call.assert_called_once()
        status_call.assert_not_called()
        body=json.loads(output.getvalue())
        self.assertEqual(body["core_status"],"SAFE_NO_NEW_OBSERVATION")
        self.assertEqual(body["live_order_submission"],"DISABLED")

    def test_cli_requires_exactly_one_mode(self):
        with self.assertRaises(SystemExit):
            main([])
        with self.assertRaises(SystemExit):
            main(["--once","--status"])


if __name__=="__main__":
    unittest.main()

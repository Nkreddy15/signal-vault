"""Phase 29 multi-market foundation tests: no live/order capability."""
from __future__ import annotations

import json
import unittest
from urllib.parse import urlparse

from signal_vault.kalshi_public_research import (
    KalshiPublicResearchClient,research_safety_receipt,
)
from signal_vault.market_capabilities import current_market_capabilities

class MultiMarketCapabilityTests(unittest.TestCase):
    def test_all_three_market_lanes_exist_and_live_is_unavailable(self):
        result=current_market_capabilities()
        self.assertEqual(
            {x["market"] for x in result["markets"]},
            {"crypto","us_equity","kalshi_event_contract"})
        self.assertEqual(result["automatic_live_trading"],"DISABLED")
        self.assertEqual(result["live_trading"],"UNAVAILABLE")
        for lane in result["markets"]:
            self.assertFalse(lane["live_execution"])
            self.assertEqual(lane["order_submission"],"DISABLED")

class KalshiPublicResearchAdapterTests(unittest.TestCase):
    def setUp(self):
        self.requests=[]
        def transport(request,timeout):
            self.requests.append((request,timeout))
            path=urlparse(request.full_url).path
            if path.endswith("/historical/cutoff"):
                return json.dumps({
                    "market_settled_ts":"2026-01-01T00:00:00Z",
                    "trades_created_ts":"2026-01-01T00:00:00Z",
                    "orders_updated_ts":"2026-01-01T00:00:00Z",
                }).encode()
            if path.endswith("/historical/markets"):
                return b'{"markets":[],"cursor":""}'
            if path.endswith("/historical/trades"):
                return b'{"trades":[],"cursor":""}'
            if path.endswith("/markets"):
                return b'{"markets":[],"cursor":""}'
            raise AssertionError(path)
        self.client=KalshiPublicResearchClient(transport=transport)

    def test_only_get_public_research_endpoints_and_no_credentials(self):
        self.client.historical_cutoff()
        self.client.historical_markets(series_ticker="KXBTC")
        self.client.historical_trades(ticker="EXAMPLE",min_ts=1,max_ts=2)
        self.client.live_public_markets()
        self.assertEqual(len(self.requests),4)
        for request,timeout in self.requests:
            self.assertEqual(request.get_method(),"GET")
            self.assertNotIn("KALSHI-ACCESS-KEY",request.headers)
            self.assertLessEqual(timeout,30)
        safety=research_safety_receipt()
        self.assertEqual(safety["credentials_accessed"],"NONE")
        self.assertEqual(safety["broker_order_submission"],"DISABLED")
        self.assertEqual(safety["demo_order_submission"],"DISABLED")
        self.assertEqual(safety["live_trading"],"UNAVAILABLE")

    def test_hosts_paths_limits_and_reversed_time_fail_closed(self):
        with self.assertRaises(ValueError):
            KalshiPublicResearchClient(base_url="https://evil.example/trade-api/v2")
        with self.assertRaises(ValueError):
            self.client.historical_markets(limit=1001)
        with self.assertRaises(ValueError):
            self.client.historical_trades(min_ts=10,max_ts=9)
        with self.assertRaises(ValueError):
            self.client._get("https://evil.example/markets")

if __name__=="__main__":
    unittest.main()

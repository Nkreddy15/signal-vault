"""Long-horizon historical research acceleration stays bounded/no-order."""
from __future__ import annotations

import json
import unittest
from datetime import date,datetime,timezone
from urllib.parse import urlparse,parse_qs

from signal_vault.historical_equity_chunks import long_horizon_equity_plan
from signal_vault.kalshi_public_research import KalshiPublicResearchClient

class LongEquityPlanTests(unittest.TestCase):
    def test_one_year_is_split_into_existing_safe_session_chunks(self):
        result=long_horizon_equity_plan(
            start_date=date(2025,10,1),
            end_date_exclusive=date(2026,9,26),
            as_of=datetime(2026,9,30,tzinfo=timezone.utc))
        self.assertGreater(result["total_sessions"],200)
        self.assertGreater(result["total_complete_core_hours_per_symbol"],1000)
        self.assertLessEqual(result["chunk_count"],20)
        self.assertTrue(all(1<=x["session_count"]<=25 for x in result["chunks"]))
        self.assertEqual(result["broker_order_submission"],"DISABLED")
        self.assertEqual(result["network_requests"],0)

    def test_overlong_window_refused(self):
        with self.assertRaises(ValueError):
            long_horizon_equity_plan(
                start_date=date(2024,1,1),
                end_date_exclusive=date(2026,1,1),
                as_of=datetime(2026,9,30,tzinfo=timezone.utc))

class KalshiHistoricalDepthTests(unittest.TestCase):
    def test_candles_and_paginated_trades_remain_get_only(self):
        seen=[]
        cursors=["next",""]
        def transport(request,timeout):
            seen.append(request)
            path=urlparse(request.full_url).path
            if path.endswith("/candlesticks"):
                return b'{"candlesticks":[]}'
            if path.endswith("/historical/trades"):
                cursor=cursors.pop(0)
                return json.dumps({"trades":[],"cursor":cursor}).encode()
            raise AssertionError(path)
        client=KalshiPublicResearchClient(transport=transport)
        client.historical_market_candlesticks(
            ticker="KXBTC-TEST",start_ts=1,end_ts=3601,period_interval=60)
        pages=client.collect_historical_trades(
            ticker="KXBTC-TEST",min_ts=1,max_ts=3601,max_pages=3)
        self.assertEqual(len(pages),2)
        self.assertEqual(len(seen),3)
        self.assertTrue(all(x.get_method()=="GET" for x in seen))
        self.assertTrue(all("KALSHI-ACCESS-KEY" not in x.headers for x in seen))

    def test_invalid_candle_and_page_bounds_fail_closed(self):
        client=KalshiPublicResearchClient(
            transport=lambda request,timeout:b'{}')
        with self.assertRaises(ValueError):
            client.historical_market_candlesticks(
                ticker="../BAD",start_ts=1,end_ts=2)
        with self.assertRaises(ValueError):
            client.historical_market_candlesticks(
                ticker="GOOD",start_ts=2,end_ts=1)
        with self.assertRaises(ValueError):
            client.collect_historical_trades(max_pages=0)

if __name__=="__main__":
    unittest.main()

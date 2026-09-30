import tempfile
import unittest
from pathlib import Path

from signal_vault.kalshi_resolved_market_evidence import (
    capture_resolved_market_evidence,
)


class FakeClient:
    def historical_market(self,ticker):
        return {"market":{
            "ticker":ticker,
            "status":"settled",
            "result":"yes",
            "settlement_ts":"2026-01-02T00:00:00Z",
            "settlement_value_dollars":"1.0000",
        }}
    def historical_market_candlesticks(self,**kwargs):
        return {"candlesticks":[{"end_period_ts":kwargs["end_ts"]}]}
    def historical_trades(self,**kwargs):
        cursor=kwargs.get("cursor")
        if cursor is None:
            return {"trades":[{"trade_id":"1"}],"cursor":"next"}
        return {"trades":[{"trade_id":"2"}],"cursor":""}


class KalshiResolvedMarketEvidenceTests(unittest.TestCase):
    def test_exact_market_capture_is_private_bounded_and_no_order(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"resolved"
            result=capture_resolved_market_evidence(
                client=FakeClient(),
                ticker="TEST-MARKET",
                start_ts=100,
                end_ts=1000,
                output_root=root,
                max_trade_pages=3,
            )
            self.assertEqual(result["ticker"],"TEST-MARKET")
            self.assertEqual(result["resolved_result"],"yes")
            self.assertEqual(result["settlement_ts"],"2026-01-02T00:00:00Z")
            self.assertEqual(len(result["trade_pages"]),2)
            self.assertTrue((root/"market.json").exists())
            self.assertEqual(result["credentials_accessed"],"NONE")
            self.assertEqual(result["demo_order_submission"],"DISABLED")
            self.assertEqual(result["live_order_submission"],"DISABLED")
            self.assertTrue((root/"manifest.json").exists())
            self.assertEqual(root.stat().st_mode & 0o077,0)

    def test_unresolved_or_wrong_market_metadata_fails_closed(self):
        class Unresolved(FakeClient):
            def historical_market(self,ticker):
                return {"market":{
                    "ticker":ticker,"status":"open","result":"",
                    "settlement_ts":None,
                }}
        class WrongTicker(FakeClient):
            def historical_market(self,ticker):
                return {"market":{
                    "ticker":"OTHER","status":"settled","result":"no",
                    "settlement_ts":"2026-01-02T00:00:00Z",
                }}
        for client in (Unresolved(),WrongTicker()):
            with tempfile.TemporaryDirectory() as td:
                with self.subTest(client=type(client).__name__), self.assertRaises(ValueError):
                    capture_resolved_market_evidence(
                        client=client,
                        ticker="TEST",
                        start_ts=100,
                        end_ts=1000,
                        output_root=Path(td)/"out",
                        max_trade_pages=3,
                    )

    def test_ticker_time_and_page_bounds_fail_closed(self):
        cases=(
            {"ticker":"bad ticker","start_ts":100,"end_ts":1000,"max_trade_pages":3},
            {"ticker":"TEST","start_ts":1000,"end_ts":100,"max_trade_pages":3},
            {"ticker":"TEST","start_ts":100,"end_ts":1000,"max_trade_pages":0},
        )
        for index,kwargs in enumerate(cases):
            with tempfile.TemporaryDirectory() as td:
                with self.subTest(index=index), self.assertRaises(ValueError):
                    capture_resolved_market_evidence(
                        client=FakeClient(),
                        output_root=Path(td)/"out",
                        **kwargs,
                    )

    def test_repeated_trade_cursor_is_rejected(self):
        class Loop(FakeClient):
            def historical_trades(self,**kwargs):
                return {"trades":[],"cursor":"same"}
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                capture_resolved_market_evidence(
                    client=Loop(),
                    ticker="TEST",
                    start_ts=100,
                    end_ts=1000,
                    output_root=Path(td)/"out",
                    max_trade_pages=3,
                )

if __name__=="__main__":
    unittest.main()

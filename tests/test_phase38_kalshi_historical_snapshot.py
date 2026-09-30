import tempfile
import unittest
from pathlib import Path

from signal_vault.kalshi_historical_snapshot import collect_historical_market_catalog


class FakeClient:
    def __init__(self):
        self.calls=[]
    def historical_cutoff(self):
        return {"historical_cutoff_ts":123}
    def historical_markets(self,*,limit=1000,cursor=None,series_ticker=None,event_ticker=None):
        self.calls.append((limit,cursor,series_ticker,event_ticker))
        if cursor is None:
            return {"markets":[{"ticker":"A"}],"cursor":"next"}
        return {"markets":[{"ticker":"B"}],"cursor":""}


class KalshiHistoricalSnapshotTests(unittest.TestCase):
    def test_catalog_is_bounded_private_and_no_order(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"kalshi"
            client=FakeClient()
            result=collect_historical_market_catalog(
                client=client,output_root=root,max_pages=3
            )
            self.assertEqual(len(result["market_pages"]),2)
            self.assertEqual(result["credentials_accessed"],"NONE")
            self.assertEqual(result["broker_order_submission"],"DISABLED")
            self.assertEqual(result["demo_order_submission"],"DISABLED")
            self.assertEqual(result["live_trading"],"UNAVAILABLE")
            self.assertTrue((root/"manifest.json").is_file())
            self.assertEqual(root.stat().st_mode & 0o077,0)
            for path in root.iterdir():
                self.assertEqual(path.stat().st_mode & 0o077,0)

    def test_repeated_cursor_fails_closed(self):
        class LoopClient(FakeClient):
            def historical_markets(self,**kwargs):
                return {"markets":[],"cursor":"same"}
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                collect_historical_market_catalog(
                    client=LoopClient(),output_root=Path(td)/"k",max_pages=3
                )

    def test_scope_and_page_bounds_are_strict(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"k"
            with self.assertRaises(ValueError):
                collect_historical_market_catalog(
                    client=FakeClient(),output_root=root,max_pages=0
                )
            with self.assertRaises(ValueError):
                collect_historical_market_catalog(
                    client=FakeClient(),output_root=root,
                    series_ticker="SERIES",event_ticker="EVENT"
                )
            with self.assertRaises(ValueError):
                collect_historical_market_catalog(
                    client=FakeClient(),output_root=root,series_ticker="bad ticker"
                )

if __name__=="__main__":
    unittest.main()

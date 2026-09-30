import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from signal_vault.kalshi_corpus_capture import (
    capture_and_validate_kalshi_corpus,
)


def write(path,obj):
    raw=(json.dumps(obj,sort_keys=True,separators=(",",":"))+"\n").encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    return hashlib.sha256(raw).hexdigest()


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00","Z")


class FakeClient:
    def __init__(self, markets, *, flip_result=False):
        self.markets=markets
        self.flip_result=flip_result
        self.calls=[]

    def historical_market(self,ticker):
        self.calls.append(("market",ticker))
        market=dict(self.markets[ticker])
        if self.flip_result and ticker=="TEST-01":
            market["result"]="no" if market["result"]=="yes" else "yes"
        return {"market":market}

    def historical_market_candlesticks(
        self,*,ticker,start_ts,end_ts,period_interval=60,
    ):
        self.calls.append(("candles",ticker))
        points=[
            (end_ts-30*3600,"0.4000"),
            (end_ts-7*3600,"0.5500"),
            (end_ts-2*3600,"0.7000"),
        ]
        return {
            "ticker":ticker,
            "candlesticks":[{
                "end_period_ts":at,
                "price":{
                    "open":price,"low":price,"high":price,"close":price,
                    "mean":price,"previous":price,
                },
                "yes_bid":{
                    "open":"0.3900","low":"0.3900",
                    "high":"0.3900","close":"0.3900",
                },
                "yes_ask":{
                    "open":"0.4100","low":"0.4100",
                    "high":"0.4100","close":"0.4100",
                },
                "volume":"10",
                "open_interest":"20",
            } for at,price in points],
        }

    def historical_trades(self,**kwargs):
        self.calls.append(("trades",kwargs["ticker"]))
        return {
            "trades":[{
                "trade_id":"t-"+kwargs["ticker"],
                "ticker":kwargs["ticker"],
            }],
            "cursor":"",
        }


class KalshiCorpusCapturePipelineTests(unittest.TestCase):
    def make_catalog(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)/"catalog"
        root.mkdir(mode=0o700)
        base=datetime(2026,1,10,tzinfo=timezone.utc)
        markets={}
        for i,result in enumerate(("yes","no"),1):
            settled=base+timedelta(days=i)
            ticker=f"TEST-{i:02d}"
            markets[ticker]={
                "ticker":ticker,
                "event_ticker":f"EVENT-{i:02d}",
                "status":"settled",
                "result":result,
                "open_time":iso(settled-timedelta(days=3)),
                "settlement_ts":iso(settled),
                "settlement_value_dollars":
                    "1.0000" if result=="yes" else "0.0000",
                "mve_collection_ticker":None,
            }
        page={"markets":list(markets.values()),"cursor":""}
        page_sha=write(root/"markets-page-001.json",page)
        cutoff_sha=write(root/"historical_cutoff.json",{"historical_cutoff_ts":1})
        manifest={
            "kind":"IMMUTABLE_KALSHI_PUBLIC_HISTORICAL_MARKET_CATALOG",
            "source":"kalshi_public_historical_GET_only",
            "cutoff_sha256":cutoff_sha,
            "market_pages":[{"page":1,"sha256":page_sha}],
            "series_ticker":None,
            "event_ticker":None,
            "credentials_accessed":"NONE",
            "authenticated_portfolio_access":"DISABLED",
            "broker_order_submission":"DISABLED",
            "demo_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        }
        write(root/"manifest.json",manifest)
        return root,markets

    def test_catalog_to_corpus_validation_is_get_only_and_hash_bound(self):
        catalog,markets=self.make_catalog()
        with tempfile.TemporaryDirectory() as td:
            output=Path(td)/"corpus"
            client=FakeClient(markets)
            result=capture_and_validate_kalshi_corpus(
                catalog_root=catalog,
                output_root=output,
                client=client,
                sample_size=2,
                max_trade_pages=3,
            )
            self.assertEqual(result["sample_size"],2)
            self.assertEqual(
                result["corpus_report"]["resolved_market_count"],2
            )
            self.assertEqual(
                result["corpus_report"]["yes_outcome_count"],1
            )
            self.assertEqual(
                result["corpus_report"]["no_outcome_count"],1
            )
            self.assertTrue((output/"manifest.json").is_file())
            self.assertTrue((output/"corpus_plan.json").is_file())
            self.assertTrue((output/"corpus_validation.json").is_file())
            self.assertEqual(output.stat().st_mode & 0o077,0)
            self.assertEqual(result["network_methods"],["GET"])
            self.assertEqual(result["demo_order_submission"],"DISABLED")
            self.assertEqual(result["live_order_submission"],"DISABLED")
            self.assertTrue(
                all(call[0] in {"market","candles","trades"}
                    for call in client.calls)
            )

    def test_settlement_result_drift_against_fixed_catalog_plan_fails(self):
        catalog,markets=self.make_catalog()
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                capture_and_validate_kalshi_corpus(
                    catalog_root=catalog,
                    output_root=Path(td)/"corpus",
                    client=FakeClient(markets,flip_result=True),
                    sample_size=2,
                    max_trade_pages=3,
                )

    def test_output_root_and_sample_bounds_fail_closed(self):
        catalog,markets=self.make_catalog()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"existing"
            root.mkdir()
            with self.assertRaises(ValueError):
                capture_and_validate_kalshi_corpus(
                    catalog_root=catalog,
                    output_root=root,
                    client=FakeClient(markets),
                    sample_size=2,
                )
            with self.assertRaises(ValueError):
                capture_and_validate_kalshi_corpus(
                    catalog_root=catalog,
                    output_root=Path(td)/"new",
                    client=FakeClient(markets),
                    sample_size=0,
                )


if __name__=="__main__":
    unittest.main()

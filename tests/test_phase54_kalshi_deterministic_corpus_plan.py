import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from signal_vault.kalshi_corpus_plan import plan_resolved_market_corpus


def write(path,obj):
    raw=(json.dumps(obj,sort_keys=True,separators=(",",":"))+"\n").encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    return hashlib.sha256(raw).hexdigest()


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00","Z")


class KalshiDeterministicCorpusPlanTests(unittest.TestCase):
    def make_catalog(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)/"catalog"
        root.mkdir(mode=0o700)
        base=datetime(2026,1,1,tzinfo=timezone.utc)
        markets=[]
        for i in range(8):
            settled=base+timedelta(days=10+i)
            markets.append({
                "ticker":f"TEST-{i:02d}",
                "event_ticker":f"EVENT-{i:02d}",
                "status":"settled",
                "result":"yes" if i%2==0 else "no",
                "open_time":iso(settled-timedelta(days=3)),
                "settlement_ts":iso(settled),
                "mve_collection_ticker":None,
            })
        # Structurally ineligible examples must not enter the sample.
        markets.extend([
            {
                "ticker":"TOO-SHORT","status":"settled","result":"yes",
                "open_time":iso(base),"settlement_ts":iso(base+timedelta(hours=20)),
                "mve_collection_ticker":None,
            },
            {
                "ticker":"OPEN-MARKET","status":"open","result":"",
                "open_time":iso(base),"settlement_ts":None,
                "mve_collection_ticker":None,
            },
            {
                "ticker":"MVE-MARKET","status":"settled","result":"no",
                "open_time":iso(base),"settlement_ts":iso(base+timedelta(days=3)),
                "mve_collection_ticker":"MVE-COLLECTION",
            },
        ])
        page={"markets":markets,"cursor":""}
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
        return root

    def test_selection_is_recent_structural_and_not_outcome_directed(self):
        result=plan_resolved_market_corpus(self.make_catalog(),sample_size=5)
        self.assertEqual(result["selected_market_count"],5)
        self.assertEqual(
            [x["ticker"] for x in result["markets"]],
            ["TEST-07","TEST-06","TEST-05","TEST-04","TEST-03"],
        )
        self.assertFalse(result["selection_order_uses_outcome_direction"])
        self.assertFalse(result["selection_order_uses_historical_price_or_pnl"])
        self.assertEqual(
            {x["resolved_result_for_scoring_only"] for x in result["markets"]},
            {"yes","no"},
        )
        self.assertEqual(result["network_requests"],"NONE")
        self.assertEqual(result["live_order_submission"],"DISABLED")

    def test_tampered_catalog_page_and_oversized_requested_sample_fail_closed(self):
        root=self.make_catalog()
        path=root/"markets-page-001.json"
        path.write_bytes(path.read_bytes()+b" ")
        with self.assertRaises(ValueError):
            plan_resolved_market_corpus(root,sample_size=5)

        with self.assertRaises(ValueError):
            plan_resolved_market_corpus(self.make_catalog(),sample_size=9)

    def test_duplicate_market_across_pages_is_rejected(self):
        root=self.make_catalog()
        first=json.loads((root/"markets-page-001.json").read_text())
        duplicate={"markets":[first["markets"][0]],"cursor":""}
        sha=write(root/"markets-page-002.json",duplicate)
        manifest=json.loads((root/"manifest.json").read_text())
        manifest["market_pages"].append({"page":2,"sha256":sha})
        write_path=root/"manifest.json"
        write_path.unlink()
        write(write_path,manifest)
        with self.assertRaises(ValueError):
            plan_resolved_market_corpus(root,sample_size=5)


if __name__=="__main__":
    unittest.main()

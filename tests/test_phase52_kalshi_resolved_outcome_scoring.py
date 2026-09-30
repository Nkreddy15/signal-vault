import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from signal_vault.offline_kalshi_resolved_validation import (
    score_resolved_market_evidence,
)


def write_json(path, value):
    raw=(json.dumps(value,sort_keys=True,separators=(",",":"))+"\n").encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    return hashlib.sha256(raw).hexdigest()


class KalshiResolvedOutcomeScoringTests(unittest.TestCase):
    def make_bundle(self, *, result="yes", post_settlement=False):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)/"evidence"
        root.mkdir(mode=0o700)
        settlement="2026-01-02T00:00:00Z"
        settled=int(datetime(2026,1,2,tzinfo=timezone.utc).timestamp())

        metadata={"market":{
            "ticker":"TEST-MARKET",
            "status":"settled",
            "result":result,
            "settlement_ts":settlement,
            "settlement_value_dollars":"1.0000" if result=="yes" else "0.0000",
        }}
        metadata_sha=write_json(root/"market.json",metadata)

        last_ts=settled+1 if post_settlement else settled-1800
        candles={"ticker":"TEST-MARKET","candlesticks":[
            {"end_period_ts":settled-90000,
             "price":{"open":"0.3900","low":"0.3800","high":"0.4100","close":"0.4000"},
             "yes_bid":{"open":"0.38","low":"0.37","high":"0.40","close":"0.39"},
             "yes_ask":{"open":"0.40","low":"0.39","high":"0.42","close":"0.41"},
             "volume":"10","open_interest":"20"},
            {"end_period_ts":settled-20000,
             "price":{"open":"0.5500","low":"0.5400","high":"0.6100","close":"0.6000"},
             "yes_bid":{"open":"0.54","low":"0.53","high":"0.60","close":"0.59"},
             "yes_ask":{"open":"0.56","low":"0.55","high":"0.62","close":"0.61"},
             "volume":"12","open_interest":"22"},
            {"end_period_ts":last_ts,
             "price":{"open":"0.7000","low":"0.6900","high":"0.7600","close":"0.7500"},
             "yes_bid":{"open":"0.69","low":"0.68","high":"0.75","close":"0.74"},
             "yes_ask":{"open":"0.71","low":"0.70","high":"0.77","close":"0.76"},
             "volume":"15","open_interest":"25"},
        ]}
        candle_sha=write_json(root/"candlesticks.json",candles)

        trade={"trades":[{"trade_id":"t1","ticker":"TEST-MARKET"}],"cursor":""}
        trade_sha=write_json(root/"trades-page-001.json",trade)
        manifest={
            "kind":"IMMUTABLE_KALSHI_RESOLVED_MARKET_PUBLIC_EVIDENCE",
            "ticker":"TEST-MARKET",
            "start_ts":settled-100000,
            "end_ts":settled,
            "candlestick_interval":60,
            "market_metadata_sha256":metadata_sha,
            "resolved_result":result,
            "settlement_ts":settlement,
            "candlesticks_sha256":candle_sha,
            "trade_pages":[{"page":1,"sha256":trade_sha}],
            "credentials_accessed":"NONE",
            "authenticated_portfolio_access":"DISABLED",
            "demo_order_submission":"DISABLED",
            "live_order_submission":"DISABLED",
        }
        write_json(root/"manifest.json",manifest)
        return root

    def test_fixed_horizons_score_only_information_available_before_settlement(self):
        root=self.make_bundle()
        result=score_resolved_market_evidence(root)
        self.assertEqual(result["resolved_result"],"yes")
        self.assertEqual(result["available_horizon_count"],3)
        scores={
            row["horizon_seconds_before_settlement"]:row
            for row in result["fixed_horizon_scores"]
        }
        self.assertEqual(scores[86400]["yes_probability"],"0.4000")
        self.assertEqual(scores[86400]["brier_error"],"0.36000000")
        self.assertEqual(scores[21600]["yes_probability"],"0.4000")
        self.assertEqual(scores[3600]["yes_probability"],"0.6000")
        self.assertEqual(scores[3600]["brier_error"],"0.16000000")
        self.assertTrue(result["score_is_market_price_calibration_not_strategy_alpha"])
        self.assertFalse(result["historical_orderbook_depth_reconstructed"])
        self.assertFalse(result["strategy_selection_performed"])
        self.assertEqual(result["demo_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")

    def test_no_outcome_uses_zero_target(self):
        root=self.make_bundle(result="no")
        result=score_resolved_market_evidence(
            root,horizons_seconds=(86400,)
        )
        row=result["fixed_horizon_scores"][0]
        self.assertEqual(row["yes_probability"],"0.4000")
        self.assertEqual(row["brier_error"],"0.16000000")

    def test_post_settlement_candle_and_tampered_source_fail_closed(self):
        with self.assertRaises(ValueError):
            score_resolved_market_evidence(self.make_bundle(post_settlement=True))

        root=self.make_bundle()
        path=root/"candlesticks.json"
        path.write_bytes(path.read_bytes()+b" ")
        with self.assertRaises(ValueError):
            score_resolved_market_evidence(root)

    def test_bad_horizon_contract_fails_closed(self):
        root=self.make_bundle()
        for horizons in ((),(0,),(3600,3600)):
            with self.subTest(horizons=horizons), self.assertRaises(ValueError):
                score_resolved_market_evidence(root,horizons_seconds=horizons)


if __name__=="__main__":
    unittest.main()

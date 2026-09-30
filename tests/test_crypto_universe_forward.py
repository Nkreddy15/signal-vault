"""Six-asset prospective journal: CLOSED clock, full SHA chain, no orders."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.crypto_universe_forward import (
    CRYPTO_SIX, ROOT, collect_six_crypto_once, universe_status,
)
from signal_vault.multi_asset_historical import HistoricalDataBatch
from signal_vault.research_universe import ResearchBar

HOUR=timedelta(hours=1)
FIRST=datetime(2026,9,29,12,7,tzinfo=timezone.utc)


class FixtureSixCryptoProvider:
    def __init__(self, *, missing=None, incorrect_feed=False):
        self.calls=[]
        self.missing=missing
        self.incorrect_feed=incorrect_feed

    def fetch(self,*,specs,start,end,as_of,**kwargs):
        self.calls.append((tuple(s.symbol for s in specs),start,end,as_of))
        n=int((end-start)/HOUR)
        rows={}
        for index,sym in enumerate(sorted(s.symbol for s in specs)):
            values=[]
            for hour in range(n):
                if self.missing==sym and hour==n-1:
                    continue
                price=Decimal(100+10*index+hour)
                values.append(ResearchBar(
                    sym,start+hour*HOUR,price,price+2,price-2,
                    price,Decimal("6.5"),
                    ("wrong_feed" if self.incorrect_feed and sym==CRYPTO_SIX[-1]
                     else "alpaca_crypto_us"),
                    as_of,False))
            rows[sym]=tuple(values)
        return HistoricalDataBatch(
            "crypto",tuple(sorted(s.symbol for s in specs)),
            "alpaca_crypto_us","not_applicable",
            start.isoformat(),end.isoformat(),as_of.isoformat(),1,rows)


class IndependentSixCryptoSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)/"new-SEPARATE-universe-volume"
        self.base.mkdir(mode=0o700)
        self.provider=FixtureSixCryptoProvider()
        self.factory_calls=0

    def factory(self):
        self.factory_calls+=1
        return self.provider

    def tick(self,now):
        return collect_six_crypto_once(
            root=self.base,now=now,provider_factory=self.factory)

    def test_baseline_72_hours_is_zero_prospective_then_six_per_one_clock_hour(self):
        self.assertEqual(universe_status(root=self.base)["status"],
                         "NO_UNIVERSE_EVIDENCE_YET")
        first=self.tick(FIRST)
        self.assertEqual(first["status"],"HISTORICAL_BASELINE_ONLY_ZERO_PROSPECTIVE")
        self.assertEqual(first["recorded_prospective_asset_bars"],0)
        self.assertEqual(first["recorded_distinct_prospective_UTC_hours"],0)
        self.assertEqual(len(self.provider.calls),1)
        self.assertEqual(self.provider.calls[0][1],FIRST.replace(minute=0)-72*HOUR)
        self.assertEqual(self.provider.calls[0][2],FIRST.replace(minute=0))
        self.assertEqual(len(self.provider.calls[0][0]),6)
        early=universe_status(root=self.base)
        self.assertEqual(early["historical_bootstrap_count"],1)
        self.assertEqual(early["current_segment_independent_prospective_hours"],0)
        self.assertFalse(early["ready_for_seven_day_audit"])

        second=self.tick(FIRST+HOUR)
        self.assertEqual(second["status"],
                         "SIX_NEW_PROSPECTIVE_ASSET_BARS_ONE_CLOCK_HOUR")
        self.assertEqual(second["recorded_prospective_asset_bars"],6)
        self.assertEqual(second["recorded_distinct_prospective_UTC_hours"],1)
        self.assertEqual(self.provider.calls[1][2]-self.provider.calls[1][1],HOUR)
        self.assertEqual(len(self.provider.calls),2)
        status=universe_status(root=self.base)
        self.assertEqual(status["all_segments_total_receipts"],2)
        self.assertEqual(status["current_segment_independent_prospective_hours"],1)
        self.assertEqual(status["current_segment_prospective_asset_bar_count"],6)
        self.assertEqual(status["segment_index"],1)
        self.assertEqual(status["broker_order_submission"],"DISABLED")
        self.assertEqual(status["network_requests"],"NONE")
        self.assertEqual(len(status["last_receipt_sha256"]),64)
        self.assertNotEqual(second["source_SHA256"],second["receipt_SHA256"])
        paths=sorted((self.base/"hourly-receipts").glob("*.json"))
        self.assertTrue(all(p.stat().st_mode&0o777==0o600 for p in paths))
        raw=json.loads(paths[-1].read_bytes())
        self.assertEqual(set(raw["source_historical_batch"]["bars"]),set(CRYPTO_SIX))
        self.assertEqual(raw["previous_receipt_sha256"],
                         json.loads(paths[0].read_bytes())["receipt_sha256"])
        self.assertEqual(set(raw["per_asset_observation_sha256"]),set(CRYPTO_SIX))
        self.assertFalse(raw["source_historical_batch"]["bars"]["BTC/USD"][0]["prospective"])
        self.assertEqual(raw["prospective_asset_rows_in_this_receipt"],6)

    def test_duplicate_wrong_time_and_rollback_make_zero_provider_calls(self):
        self.assertEqual(self.tick(FIRST-timedelta(minutes=5))["status"],
                         "SAFE_SKIP_OUTSIDE_FRESH_CLOSED_HOUR_WINDOW")
        self.assertEqual(self.factory_calls,0)
        self.tick(FIRST)
        self.assertEqual(self.factory_calls,1)
        again=self.tick(FIRST+timedelta(minutes=4))
        self.assertEqual(again["status"],"SAFE_DUPLICATE_OR_CLOCK_ROLLBACK_NO_GET")
        self.assertEqual(self.factory_calls,1)
        self.assertEqual(
            self.tick(FIRST+HOUR-timedelta(minutes=10))["status"],
            "SAFE_SKIP_OUTSIDE_FRESH_CLOSED_HOUR_WINDOW")
        self.assertEqual(self.factory_calls,1)
        self.assertEqual(
            self.tick(FIRST-HOUR)["status"],"SAFE_DUPLICATE_OR_CLOCK_ROLLBACK_NO_GET")
        self.assertEqual(self.factory_calls,1)

    def test_gap_bootstraps_new_zero_prospective_segment_without_backfill(self):
        self.tick(FIRST)
        self.tick(FIRST+HOUR)
        missed=self.tick(FIRST+4*HOUR)
        self.assertEqual(missed["event"],"HISTORICAL_72H_BOOTSTRAP")
        self.assertEqual(missed["segment_index"],2)
        self.assertEqual(missed["recorded_prospective_asset_bars"],0)
        state=universe_status(root=self.base)
        self.assertEqual(state["all_segments_total_receipts"],3)
        self.assertEqual(state["historical_bootstrap_count"],2)
        self.assertEqual(state["current_segment_independent_prospective_hours"],0)
        self.assertEqual(self.provider.calls[-1][2]-self.provider.calls[-1][1],72*HOUR)
        next_=self.tick(FIRST+5*HOUR)
        self.assertEqual(next_["recorded_prospective_asset_bars"],6)
        state=universe_status(root=self.base)
        self.assertEqual(state["all_segments_total_receipts"],4)
        self.assertEqual(state["current_segment_independent_prospective_hours"],1)
        self.assertEqual(state["current_segment_prospective_asset_bar_count"],6)
        self.assertEqual(state["segment_index"],2)
        self.assertEqual(state["historical_bootstrap_count"],2)

    def test_corrupted_or_deleted_prior_receipt_prevents_credential_factory(self):
        self.tick(FIRST)
        self.tick(FIRST+HOUR)
        items=sorted((self.base/"hourly-receipts").glob("*.json"))
        raw=json.loads(items[0].read_text())
        raw["source_historical_batch"]["bars"]["BTC/USD"][0]["close"]="9999999999"
        items[0].write_text(json.dumps(raw,sort_keys=True)+"\n")
        before=self.factory_calls
        with self.assertRaises(ValueError):
            self.tick(FIRST+2*HOUR)
        self.assertEqual(self.factory_calls,before)
        with self.assertRaises(ValueError):
            universe_status(root=self.base)

    def test_extra_receipt_symlink_and_unsafe_permissions_prevent_new_GET(self):
        self.tick(FIRST)
        folder=self.base/"hourly-receipts"
        (folder/"unexpected.tmp").write_text("unexpected")
        with self.assertRaises(ValueError):
            self.tick(FIRST+HOUR)
        self.assertEqual(self.factory_calls,1)
        (folder/"unexpected.tmp").unlink()
        file=next(folder.iterdir())
        file.chmod(0o644)
        with self.assertRaises(ValueError):
            universe_status(root=self.base)
        self.assertEqual(self.factory_calls,1)

    def test_missing_symbol_hour_and_mixed_feed_do_not_create_new_receipts(self):
        for problem in (
            FixtureSixCryptoProvider(missing="ETH/USD"),
            FixtureSixCryptoProvider(incorrect_feed=True),
        ):
            with self.subTest(problem=problem.__dict__):
                self.provider=problem
                with self.assertRaises(ValueError):
                    self.tick(FIRST)
                self.assertEqual(list((self.base/"hourly-receipts").glob("*.json")),[])
                self.assertEqual(universe_status(root=self.base)[
                    "current_segment_independent_prospective_hours"],0)
        self.provider=FixtureSixCryptoProvider()
        self.tick(FIRST)
        self.provider=FixtureSixCryptoProvider(missing="ETH/USD")
        with self.assertRaises(ValueError):
            self.tick(FIRST+HOUR)
        self.assertEqual(universe_status(root=self.base)["all_segments_total_receipts"],1)

    def test_same_volumepath_as_old_BTC_is_forbidden_without_read(self):
        with self.assertRaises(ValueError):
            collect_six_crypto_once(
                root=ROOT.parent,now=FIRST,provider_factory=self.factory)
        self.assertEqual(self.factory_calls,0)
        self.base.chmod(0o755)
        with self.assertRaises(ValueError):
            universe_status(root=self.base)
        self.assertEqual(self.factory_calls,0)


if __name__=="__main__":
    unittest.main()

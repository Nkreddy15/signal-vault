"""Synthetic offline original GitHub ZIP provenance & all-pair attribution tests.

No GitHub network, no Alpaca DATA keys, no imported order component.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.ci_historical_report import ANALYSIS_FILENAME, analyze_manual_history
from signal_vault.multi_asset_historical import HistoricalDataBatch, archive_historical_batch
from signal_vault.multi_asset_research_cli import historical_plan
from signal_vault.offline_zip_attribution import analyze_six_asset_zip
from signal_vault.research_universe import AssetClass, ResearchBar

START=datetime(2026,8,29,2,tzinfo=timezone.utc)
HOUR=timedelta(hours=1)
END=START+70*HOUR
AS_OF=END+timedelta(minutes=7)
NAMES=("AVAX/USD","BTC/USD","ETH/USD","LINK/USD","LTC/USD","SOL/USD")


class SixAssetZipOfflineAttributionTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        private=self.root/"archives"
        private.mkdir(mode=0o700)
        values={}
        for i,sym in enumerate(NAMES):
            px=Decimal(90+i*15)
            rows=[]
            for idx in range(70):
                px=px+(Decimal(idx%11)-Decimal(5))/Decimal("5")
                rows.append(ResearchBar(
                    sym,START+idx*HOUR,px,px+2,px-2,px,
                    Decimal(10),"alpaca_crypto_us",AS_OF,False,
                ))
            values[sym]=tuple(rows)
        original=HistoricalDataBatch(
            "crypto",NAMES,"alpaca_crypto_us","not_applicable",
            START.isoformat(),END.isoformat(),AS_OF.isoformat(),1,values)
        self.history=archive_historical_batch(original,output_folder=private)
        plan=historical_plan(
            symbols=NAMES,start=START,end=END,market=AssetClass.CRYPTO)
        analyze_manual_history(folder=private,plan=plan)
        self.original=private
        self.zipfile=self.root/"downloaded_private_GitHub_run.zip"
        self._zip_it()

    def _zip_it(self, *, modifications=None):
        items={
            x.name:x.read_bytes() for x in self.original.iterdir()
            if x.is_file()
        }
        if modifications is not None:
            items=modifications(items)
        with zipfile.ZipFile(self.zipfile,"w",
                             compression=zipfile.ZIP_DEFLATED) as z:
            for n,raw in sorted(items.items()):
                z.writestr(n,raw)

    def test_full_six_market_zip_validated_and_all_15_pair_scenarios_reconciled(self):
        before={x.name:x.read_bytes() for x in self.original.iterdir() if x.is_file()}
        out=analyze_six_asset_zip(self.zipfile)
        self.assertEqual(out["assets"],list(NAMES))
        self.assertEqual(out["per_asset_closed_historical_bars"],
                         {sym:70 for sym in NAMES})
        self.assertEqual(out["distinct_clock_hours"],70)
        self.assertEqual(len(out["original_historical_archives_sha256"]),1)
        self.assertTrue(out["previous_passive_comparator_only_allocated_to_first_two_symbols"])
        self.assertEqual(set(out["all_fifteen_pair_alternative_scenarios"]),
                         {"illustrative_low_friction",
                          "illustrative_base_friction",
                          "illustrative_high_friction"})
        for scenario in out["all_fifteen_pair_alternative_scenarios"].values():
            self.assertTrue(scenario["original_alphabetical_passive_PNL_exactly_reconciled"])
            self.assertEqual(
                scenario["all_pair_diagnostic"]["all_pair_summary_usd"]["scenario_count"],15)
            self.assertEqual(
                scenario["all_pair_diagnostic"]
                ["alphabetical_pair_represented_by_old_passive_baseline"],
                ["AVAX/USD","BTC/USD"])
        self.assertEqual(out["broker_order_submission"],"DISABLED")
        self.assertEqual(out["network_requests"],"NONE")
        self.assertEqual(out["credential_access"],"NONE")
        self.assertFalse(out["model_selected_on_test_performance"])
        self.assertEqual({x.name:x.read_bytes() for x in self.original.iterdir()
                          if x.is_file()},before)
        self.assertEqual(out,analyze_six_asset_zip(self.zipfile))

    def test_mismatched_original_SHA_blocks_without_modifying_source(self):
        def corrupt(items):
            original=items[self.history.name]
            items[self.history.name]=original+b"tampered"
            return items
        self._zip_it(modifications=corrupt)
        zip_before=self.zipfile.read_bytes()
        with self.assertRaises(ValueError):
            analyze_six_asset_zip(self.zipfile)
        self.assertEqual(self.zipfile.read_bytes(),zip_before)

    def test_unknown_flat_member_missing_cost_and_path_traversal_block(self):
        original=self.zipfile.read_bytes()
        def unknown(items):
            items["credentials.txt"]=b"not allowed"
            return items
        self._zip_it(modifications=unknown)
        with self.assertRaises(ValueError):
            analyze_six_asset_zip(self.zipfile)
        def missing(items):
            items.pop("cost_assumptions-illustrative_base_friction.json")
            return items
        self._zip_it(modifications=missing)
        with self.assertRaises(ValueError):
            analyze_six_asset_zip(self.zipfile)
        def traversal(items):
            items["../oops.json"]=b"no"
            return items
        self._zip_it(modifications=traversal)
        with self.assertRaises(ValueError):
            analyze_six_asset_zip(self.zipfile)

    def test_cost_assumption_changes_or_old_source_manifest_not_trusted(self):
        def wrong_cost(items):
            target="cost_assumptions-illustrative_base_friction.json"
            payload=json.loads(items[target])
            payload["BTC/USD"]["taker_fee_bps"]="0"
            items[target]=(json.dumps(payload,sort_keys=True)+"\n").encode()
            return items
        self._zip_it(modifications=wrong_cost)
        with self.assertRaises(ValueError):
            analyze_six_asset_zip(self.zipfile)
        def wrong_report(items):
            record=json.loads(items[ANALYSIS_FILENAME])
            record["historical_archive_audit"][0]["sha256"]="0"*64
            items[ANALYSIS_FILENAME]=json.dumps(record).encode()
            return items
        self._zip_it(modifications=wrong_report)
        with self.assertRaises(ValueError):
            analyze_six_asset_zip(self.zipfile)
        def future_report(items):
            record=json.loads(items[ANALYSIS_FILENAME])
            record["data_is_historical_not_new_prospective_observations"]=False
            items[ANALYSIS_FILENAME]=json.dumps(record).encode()
            return items
        self._zip_it(modifications=future_report)
        with self.assertRaises(ValueError):
            analyze_six_asset_zip(self.zipfile)

    def test_private_zip_must_not_be_directory_or_symlink(self):
        ref=self.root/"symlink.zip"
        ref.symlink_to(self.zipfile)
        with self.assertRaises(ValueError):
            analyze_six_asset_zip(ref)


if __name__=="__main__":
    unittest.main()

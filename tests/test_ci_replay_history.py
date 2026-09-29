"""No-network historical v1->v2 replay from immutable prior private run fixture."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.ci_replay_history import (
    ANALYSIS_FILENAME,MANIFEST,reanalyze_existing_history,
)
from signal_vault.multi_asset_historical import (
    HistoricalDataBatch,archive_historical_batch,
)
from signal_vault.multi_asset_research_cli import historical_plan
from signal_vault.research_universe import AssetClass,ResearchBar

END=datetime(2026,9,1,0,tzinfo=timezone.utc)
START=END-timedelta(hours=70)
CAPTURE=END+timedelta(minutes=7)
SYMBOLS=("BTC/USD","ETH/USD")


def bar(symbol,index):
    px=Decimal("100") if index<35 else Decimal("75")
    return ResearchBar(
        symbol,START+timedelta(hours=index),
        px,px+Decimal("2"),px-Decimal("2"),px,
        Decimal("10"),"alpaca_crypto_us",CAPTURE,False)


class ExistingHistoryReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.source=self.root/"downloaded-history"
        self.source.mkdir(mode=0o700)
        self.target=self.root/"private-v2-replay"
        self.plan=historical_plan(
            symbols=SYMBOLS,start=START,end=END,market=AssetClass.CRYPTO)
        self.batch=HistoricalDataBatch(
            "crypto",SYMBOLS,"alpaca_crypto_us","not_applicable",
            START.isoformat(),END.isoformat(),CAPTURE.isoformat(),2,
            {sym:tuple(bar(sym,i) for i in range(70)) for sym in SYMBOLS},
        )
        self.archive=archive_historical_batch(self.batch,output_folder=self.source)
        self.original_report={
            "kind":"HISTORICAL_MULTIASSET_SHA_BOUND_THREE_COST_SCENARIOS_NO_ORDERS",
            "schema_version":1,
            "market":"crypto",
            "symbols":list(SYMBOLS),
            "predeclared_request_windows":list(self.plan["windows"]),
            "historical_archive_audit":[{
                "filename":self.archive.name,
                "sha256":hashlib.sha256(self.archive.read_bytes()).hexdigest(),
            }],
            "broker_order_submission":"DISABLED",
            "strategy_promoted":False,
            "independent_forward_strategy_edge_established":False,
            "data_is_historical_not_new_prospective_observations":True,
        }
        self.report=self.source/ANALYSIS_FILENAME
        self.report.write_text(json.dumps(self.original_report,sort_keys=True)+"\n")
        self.report.chmod(0o600)

    def test_sha_bound_copy_and_v2_analysis_preserves_originals(self):
        raw_before=self.archive.read_bytes()
        report_before=self.report.read_bytes()
        # Simulate GitHub download-artifact permission normalization: source
        # archives may be 0644, but replay always writes private 0600 copies.
        self.archive.chmod(0o644)
        result=reanalyze_existing_history(
            source=self.source,destination=self.target,
            source_run_id=36632386959)
        self.assertEqual(result["kind"],"OFFLINE_HISTORY_RISK_V2_REPLAY_COMPLETE")
        self.assertEqual(result["source_archive_count"],1)
        self.assertEqual(result["credential_access"],"NONE")
        self.assertTrue(result["no_new_market_data_requests"])
        self.assertEqual(result["broker_order_submission"],"DISABLED")
        self.assertEqual(self.archive.read_bytes(),raw_before)
        self.assertEqual(self.report.read_bytes(),report_before)
        self.assertEqual((self.target/self.archive.name).read_bytes(),raw_before)
        self.assertEqual((self.target/self.archive.name).stat().st_mode&0o777,0o600)
        new_report=json.loads((self.target/ANALYSIS_FILENAME).read_bytes())
        self.assertEqual(new_report["simulation_accounting_version"],
                         "v2_utc_daily_reset_plus_persistent_peak_drawdown_halt")
        self.assertTrue(new_report["previous_v1_historical_outputs_are_not_directly_comparable"])
        self.assertTrue(new_report["data_is_historical_not_new_prospective_observations"])
        mapping=json.loads((self.target/MANIFEST).read_bytes())
        self.assertEqual(mapping["source_workflow_run_id"],36632386959)
        self.assertEqual(mapping["original_analysis_report_sha256"],
                         hashlib.sha256(report_before).hexdigest())
        self.assertEqual(mapping["corrected_analysis_report_sha256"],
                         hashlib.sha256((self.target/ANALYSIS_FILENAME).read_bytes()).hexdigest())
        self.assertFalse(mapping["source_archive_content_changed"])
        with self.assertRaises(ValueError):
            reanalyze_existing_history(
                source=self.source,destination=self.target,
                source_run_id=36632386959)

    def test_modified_archive_refused_before_creating_any_replay_outputs(self):
        self.archive.write_bytes(self.archive.read_bytes()+b"tampered")
        with self.assertRaises(ValueError):
            reanalyze_existing_history(
                source=self.source,destination=self.target,
                source_run_id=36632386959)
        self.assertFalse(self.target.exists())

    def test_wrong_window_plan_or_untrusted_original_is_rejected(self):
        self.original_report["predeclared_request_windows"][0]["end_utc"]=(
            END+timedelta(hours=1)).isoformat()
        self.report.write_text(json.dumps(self.original_report))
        with self.assertRaises(ValueError):
            reanalyze_existing_history(
                source=self.source,destination=self.target,
                source_run_id=36632386959)
        self.assertFalse(self.target.exists())

    def test_no_missing_archives_no_symlinks_no_arbitrary_paths(self):
        self.archive.unlink()
        with self.assertRaises(ValueError):
            reanalyze_existing_history(
                source=self.source,destination=self.target,
                source_run_id=36632386959)
        self.assertFalse(self.target.exists())
        link=self.source/self.original_report["historical_archive_audit"][0]["filename"]
        link.symlink_to(self.report)
        with self.assertRaises(ValueError):
            reanalyze_existing_history(
                source=self.source,destination=self.target,
                source_run_id=36632386959)
        self.assertFalse(self.target.exists())
        with self.assertRaises(ValueError):
            reanalyze_existing_history(
                source=self.source,destination=self.target,
                source_run_id=-1)
        self.assertFalse(self.target.exists())

    def test_original_report_sha_and_replay_versions_are_distinct(self):
        before_sha=hashlib.sha256(self.report.read_bytes()).hexdigest()
        result=reanalyze_existing_history(
            source=self.source,destination=self.target,
            source_run_id=36632386959)
        self.assertEqual(result["source_analysis_report_sha256"],before_sha)
        self.assertNotEqual(before_sha,result["corrected_analysis_report_sha256"])
        self.assertEqual(result["broker_order_submission"],"DISABLED")


if __name__=="__main__":
    unittest.main()

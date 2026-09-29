"""Offline source folders/ZIPs => true mixed-calendar common-horizon research.

All inputs synthetic and SHA-bound using our original ingestion contracts;
no GitHub API, Alpaca DATA credentials, account, paper order or live mode.
"""
from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.ci_historical_equities import execute_manual_equity_history
from signal_vault.ci_historical_report import analyze_manual_history
from signal_vault.cross_market_joint_review import CRYPTO_SIX
from signal_vault.joint_historical_source import (
    analyze_two_verified_history_artifacts,
)
from signal_vault.multi_asset_historical import (
    HistoricalDataBatch,archive_historical_batch,
)
from signal_vault.multi_asset_research_cli import historical_plan
from signal_vault.research_universe import AssetClass,ResearchBar
from test_ci_historical_equities import ENV,NOW,FakeLiquidIEXProvider

UTC=timezone.utc
HOUR=timedelta(hours=1)
CRYPTO_START=datetime(2026,9,14,tzinfo=UTC)
CRYPTO_END=datetime(2026,9,26,tzinfo=UTC)


def fake_crypto_batch():
    assets={}
    for i,sym in enumerate(CRYPTO_SIX):
        px=Decimal(100+i*10)
        assets[sym]=tuple(ResearchBar(
            sym,CRYPTO_START+HOUR*idx,
            px,px+Decimal("2"),px-Decimal("2"),px,Decimal("25"),
            "alpaca_crypto_us",NOW,False)
            for idx in range(288))
    return HistoricalDataBatch(
        "crypto",CRYPTO_SIX,"alpaca_crypto_us","not_applicable",
        CRYPTO_START.isoformat(),CRYPTO_END.isoformat(),
        NOW.isoformat(),2,assets)


class TwoIndependentArtifactTwelveMarketIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root=Path(cls.temp.name)
        cls.crypto=cls.root/"original-crypto"
        cls.stock=cls.root/"original-equity"
        cls.crypto.mkdir(mode=0o700)
        stock_run=execute_manual_equity_history(
            env=ENV,as_of=NOW,provider_factory=FakeLiquidIEXProvider,
            output_folder=cls.stock)
        assert stock_run["archive_count"]==10
        original=archive_historical_batch(
            fake_crypto_batch(),output_folder=cls.crypto)
        plan=historical_plan(
            symbols=CRYPTO_SIX,start=CRYPTO_START,end=CRYPTO_END,
            market=AssetClass.CRYPTO)
        result=analyze_manual_history(folder=cls.crypto,plan=plan)
        assert result["historical_archive_count"]==1

    def test_two_source_ARTIFACT_DIRECTORIES_validate_and_join_one_100(self):
        result=analyze_two_verified_history_artifacts(
            crypto_artifact=self.crypto,stock_artifact=self.stock,
            require_reference_stock_digest=False)
        self.assertEqual(result["kind"],
                         "OFFLINE_SYNCHRONIZED_TWELVE_ASSET_MIXED_CALENDAR_RESEARCH")
        self.assertEqual(len(result["twelve_source_data_sha256"]),12)
        self.assertEqual(
            result["stock_and_crypto_time_compatibility"][
                "common_source_closed_bar_open_hours"],60)
        self.assertEqual(result["evaluated_stock_regular_CORE_hour_opens_after_global_warmup"],32)
        self.assertEqual(result["common_research_start_utc"],
                         datetime(2026,9,18,18,tzinfo=UTC).isoformat())
        self.assertEqual(result["common_research_end_utc_exclusive"],
                         datetime(2026,9,25,20,tzinfo=UTC).isoformat())
        self.assertTrue(result["one_SHARED_100_usd_cash_not_twelve_times_100"])
        self.assertEqual(result["max_combined_long_exposure_usd"],"30")
        self.assertEqual(
            result["source_pair_provenance"][
                "new_historical_downloads_triggered_by_this_joint_analysis"],0)
        self.assertFalse(
            result["source_pair_provenance"][
                "stock_and_crypto_artifact_bytes_modified"])
        self.assertEqual(result["broker_order_submission"],"DISABLED")
        self.assertEqual(result["credential_access"],"NONE")
        self.assertEqual(result["network_requests"],"NONE")
        self.assertEqual(len(result["three_estimated_friction_scenarios"]),3)

    def test_actual_stock_reference_SHA_must_be_explicit_for_operator_mode(self):
        with self.assertRaisesRegex(ValueError,"stock history differs"):
            analyze_two_verified_history_artifacts(
                crypto_artifact=self.crypto,stock_artifact=self.stock)

    def test_forged_extracted_archive_is_refused_before_model_calculation(self):
        path=next(self.crypto.glob("historical-crypto-*.json"))
        source=path.read_bytes()
        try:
            path.write_bytes(source+b"changed")
            with self.assertRaises(ValueError):
                analyze_two_verified_history_artifacts(
                    crypto_artifact=self.crypto,stock_artifact=self.stock,
                    require_reference_stock_digest=False)
        finally:
            path.write_bytes(source)

    def test_ZIP_source_acceptance_matches_exact_same_bounded_flat_data(self):
        crypto_zip=self.root/"frozen-crypto.zip"
        stock_zip=self.root/"frozen-stock.zip"
        for src,dest in ((self.crypto,crypto_zip),(self.stock,stock_zip)):
            with zipfile.ZipFile(dest,"w",compression=zipfile.ZIP_DEFLATED) as z:
                for p in sorted(src.iterdir()):
                    z.writestr(p.name,p.read_bytes())
        report=analyze_two_verified_history_artifacts(
            crypto_artifact=crypto_zip,stock_artifact=stock_zip,
            require_reference_stock_digest=False)
        self.assertEqual(len(report["crypto_symbols"]),6)
        self.assertEqual(len(report["stock_symbols"]),6)
        self.assertEqual(report["broker_order_submission"],"DISABLED")

    def test_symlinked_artifact_directory_and_nested_file_fail_closed(self):
        link=self.root/"symlink-input"
        if link.exists() or link.is_symlink():link.unlink()
        link.symlink_to(self.stock)
        with self.assertRaises(ValueError):
            analyze_two_verified_history_artifacts(
                crypto_artifact=self.crypto,stock_artifact=link,
                require_reference_stock_digest=False)


if __name__=="__main__":
    unittest.main()

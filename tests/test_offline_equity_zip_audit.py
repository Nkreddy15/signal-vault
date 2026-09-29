"""No-network, no-key historical IEX ZIP source/calendar/result replay tests."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from signal_vault.ci_historical_equities import execute_manual_equity_history
from signal_vault.offline_equity_zip_audit import audit_equity_history_zip
from test_ci_historical_equities import ENV, NOW, FakeLiquidIEXProvider


class IndependentSixStockArtifactAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root=Path(cls.temp.name)
        original=cls.root/"synthetic-original-private-IEX"
        FakeLiquidIEXProvider.instances=[]
        FakeLiquidIEXProvider.drop_session=None
        result=execute_manual_equity_history(
            env=ENV,as_of=NOW,provider_factory=FakeLiquidIEXProvider,
            output_folder=original)
        assert result["completed_exchange_sessions"]==10
        cls.contents={p.name:p.read_bytes() for p in original.iterdir()}
        cls.artifact=cls.root/"private-six-stock-source.zip"

    def makezip(self, modify=None):
        items=dict(self.contents)
        if modify is not None:
            items=modify(items)
        with zipfile.ZipFile(
                self.artifact,"w",compression=zipfile.ZIP_DEFLATED) as z:
            for name,content in sorted(items.items()):
                z.writestr(name,content)
        return self.artifact

    def test_sha_bound_all_ten_sessions_three_costs_and_recomputed_PNL(self):
        source=self.makezip()
        before=hashlib.sha256(source.read_bytes()).hexdigest()
        result=audit_equity_history_zip(source)
        self.assertEqual(result["kind"],
                         "INDEPENDENT_OFFLINE_SIX_STOCK_IEX_HISTORY_REPRODUCIBILITY_AUDIT")
        self.assertEqual(result["regular_core_hourly_bars_per_symbol"],60)
        self.assertEqual(result["total_historical_asset_hour_records"],360)
        self.assertEqual(len(result["original_session_sha256_by_name"]),10)
        self.assertEqual(result["original_zip_sha256"],before)
        self.assertEqual(
            result["original_stock_report_sha256"],
            hashlib.sha256(self.contents["offline_equity_research.json"]).hexdigest())
        self.assertTrue(result["original_dataset_quality_sha_reproduced"])
        self.assertTrue(result["original_three_cost_scenarios_and_all_four_strategies_reproduced"])
        self.assertEqual(len(result["scenario_results"]),3)
        self.assertEqual(result["sample_adequacy"]["development_evaluated_bars"],16)
        self.assertEqual(result["sample_adequacy"]["validation_evaluated_bars"],8)
        self.assertEqual(result["sample_adequacy"]["untouched_test_evaluated_bars"],8)
        self.assertTrue(result["fractional_stock_buy_fills_in_hypothetical_books"]>0)
        self.assertTrue(result["fractional_share_tradability_or_minimums_not_provider_verified"])
        self.assertEqual(result["broker_order_submission"],"DISABLED")
        self.assertEqual(result["network_requests"],"NONE")
        self.assertEqual(result["credentials_accessed"],"NONE")
        self.assertEqual(result["all_history_retrospective_prospective_observations_verified"],0)
        self.assertEqual(result,audit_equity_history_zip(source))
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),before)

    def test_unexpected_or_missing_zip_members_refused_without_extraction(self):
        def unknown(items):
            items["credentials.txt"]=b"not a permitted data file"
            return items
        def missing(items):
            name=next(k for k in items if k.startswith("historical-"))
            items.pop(name)
            return items
        def traversal(items):
            items["../escapes.json"]=b"path traversal"
            return items
        for tamper in (unknown,missing,traversal):
            path=self.makezip(modify=tamper)
            source_copy=path.read_bytes()
            with self.subTest(action=tamper.__name__),self.assertRaises(ValueError):
                audit_equity_history_zip(path)
            self.assertEqual(path.read_bytes(),source_copy)

    def test_tampered_stock_OHLCV_or_archive_sha_rejected(self):
        def modified(items):
            name=next(k for k in items if k.startswith("historical-"))
            decoded=json.loads(items[name])
            decoded["bars"]["SPY"][0]["close"]="99999999"
            items[name]=(json.dumps(decoded,sort_keys=True)+"\n").encode()
            return items
        path=self.makezip(modify=modified)
        with self.assertRaises(ValueError):
            audit_equity_history_zip(path)

    def test_forged_calendar_cannot_be_accepted_just_by_editing_report(self):
        def modified(items):
            report=json.loads(items["offline_equity_research.json"])
            report["exchange_calendar_session_plan"]["sessions"][0][
                "exchange_open_utc"]="2026-09-14T13:00:00+00:00"
            items["offline_equity_research.json"]=json.dumps(report).encode()
            return items
        with self.assertRaises(ValueError):
            audit_equity_history_zip(self.makezip(modify=modified))

    def test_cost_rewrite_and_fake_trade_permissions_are_blocked(self):
        def cost(items):
            report=json.loads(items["offline_equity_research.json"])
            report["three_estimated_cost_scenarios"][
                "illustrative_base_equity_friction"][
                "explicit_assumptions_by_symbol"]["AAPL"][
                "taker_fee_bps"]="999"
            items["offline_equity_research.json"]=json.dumps(report).encode()
            return items
        def orders(items):
            report=json.loads(items["offline_equity_research.json"])
            report["broker_order_submission"]="ENABLED"
            items["offline_equity_research.json"]=json.dumps(report).encode()
            return items
        for change in (cost,orders):
            with self.subTest(change=change.__name__),self.assertRaises(ValueError):
                audit_equity_history_zip(self.makezip(modify=change))

    def test_source_ZIP_cannot_be_symlink_or_folder(self):
        path=self.makezip()
        link=self.root/"unsafe-alias.zip"
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(path)
        with self.assertRaises(ValueError):
            audit_equity_history_zip(link)
        with self.assertRaises(ValueError):
            audit_equity_history_zip(self.root)


if __name__=="__main__":
    unittest.main()

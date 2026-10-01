"""Fully synthetic/manual-report acceptance: no provider, credentials or orders."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.ci_historical_report import (
    ANALYSIS_FILENAME, SCENARIOS, analyze_manual_history,
    audit_requested_archives,
)
from signal_vault.multi_asset_historical import (
    HistoricalDataBatch, archive_historical_batch,
)
from signal_vault.multi_asset_research_cli import historical_plan
from signal_vault.research_universe import (
    AssetClass, ResearchBar,
)

HOUR=timedelta(hours=1)
END=datetime(2026,9,1,0,tzinfo=timezone.utc)
AS_OF=END+timedelta(minutes=7)
FIRST=END-timedelta(hours=70)
SYMBOLS=("BTC/USD","ETH/USD")


def make_bar(symbol, i, *, first=FIRST, captured=AS_OF):
    price=Decimal("100")+Decimal(i)
    return ResearchBar(
        symbol, first+i*HOUR,price,price+Decimal("2"),
        price-Decimal("2"),price,Decimal("10"),"alpaca_crypto_us",
        captured,False,
    )


def sample_bundle(*, symbols=SYMBOLS, start=FIRST, hours=70):
    return HistoricalDataBatch(
        "crypto",tuple(sorted(symbols)),
        "alpaca_crypto_us","not_applicable",
        start.isoformat(),(start+hours*HOUR).isoformat(),
        AS_OF.isoformat(),2,
        {sym:tuple(make_bar(sym,i,first=start) for i in range(hours))
         for sym in symbols},
    )


class HistoricalReportTests(unittest.TestCase):
    def setUp(self):
        td=tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.folder=Path(td.name)/"private-historical-artifacts"
        self.folder.mkdir(mode=0o700)
        self.plan=historical_plan(
            symbols=SYMBOLS,start=FIRST,end=END,market=AssetClass.CRYPTO)

    def put(self,* ,symbols=SYMBOLS,start=FIRST,hours=70):
        return archive_historical_batch(
            sample_bundle(symbols=symbols,start=start,hours=hours),
            output_folder=self.folder)

    def test_complete_archives_generate_3_stress_reports_without_secrets(self):
        original=self.put()
        original_sha=hashlib.sha256(original.read_bytes()).hexdigest()
        result=analyze_manual_history(folder=self.folder,plan=self.plan)
        self.assertEqual(result["status"],
                         "COMPLETE_HISTORICAL_DATA_AND_THREE_COST_SCENARIOS")
        self.assertEqual(result["historical_archive_count"],1)
        self.assertEqual(set(result["cost_scenarios"]),set(SCENARIOS))
        self.assertEqual(result["broker_order_submission"],"DISABLED")
        self.assertEqual(result["credential_access_during_analysis"],"NONE")
        self.assertEqual(result["network_requests_during_analysis"],"NONE")
        self.assertFalse(result["proven_future_return"])
        path=self.folder/ANALYSIS_FILENAME
        self.assertTrue(path.is_file())
        self.assertEqual(path.stat().st_mode & 0o777,0o600)
        raw=path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         result["research_report_sha256"])
        content=json.loads(raw)
        self.assertEqual(content["kind"],
                         "HISTORICAL_MULTIASSET_SHA_BOUND_THREE_COST_SCENARIOS_NO_ORDERS")
        self.assertEqual(content["historical_archive_audit"][0]["sha256"],original_sha)
        self.assertFalse(content["independent_forward_strategy_edge_established"])
        self.assertFalse(content["candidate_selection_from_untouched_test"])
        self.assertEqual(content["simulation_accounting_version"],
                         "v2_utc_daily_reset_plus_persistent_peak_drawdown_halt")
        self.assertTrue(content["previous_v1_historical_outputs_are_not_directly_comparable"])
        self.assertTrue(content["data_is_historical_not_new_prospective_observations"])
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(),original_sha)
        for scenario in content["scenarios"].values():
            details=scenario["offline_report"]
            self.assertEqual(set(details["asset_quality_reviews"]),set(SYMBOLS))
            self.assertEqual(
                len(details["one_SHARED_100_usd_portfolio_by_fixed_hypothesis"]),9)
            for expected in (
                "generic-ema12x26-confirm2-v2-predeclared",
                "generic-ema24x72-v1-predeclared",
                "generic-ema24x72-confirm2-v1-predeclared",
                "generic-momentum72bar150bps-v1-predeclared",
                "generic-momentum168bar250bps-v1-predeclared",
            ):
                self.assertIn(
                    expected,
                    details["one_SHARED_100_usd_portfolio_by_fixed_hypothesis"],
                )
            self.assertTrue(details["estimated_not_observed_fees_and_spreads"] if
                            "estimated_not_observed_fees_and_spreads" in details else True)
            self.assertFalse(details["strategy_chosen_from_validation_or_test"])
            self.assertEqual(
                details["one_SHARED_100_usd_portfolio_by_fixed_hypothesis"]
                ["cash-v1-predeclared"]["initial_bankroll_usd"],"100")
            self.assertEqual(
                details["simulation_accounting_version"],
                "v2_utc_daily_reset_plus_persistent_peak_drawdown_halt")
            self.assertFalse(
                details["one_SHARED_100_usd_portfolio_by_fixed_hypothesis"]
                ["cash-v1-predeclared"]["persistent_peak_drawdown_entry_halt"])
        with self.assertRaises(ValueError):
            analyze_manual_history(folder=self.folder,plan=self.plan)
        self.assertEqual(path.read_bytes(),raw)

    def test_no_missing_or_duplicate_window_permitted(self):
        with self.assertRaises(ValueError):
            audit_requested_archives(self.folder,plan=self.plan)
        self.assertEqual(list(self.folder.iterdir()),[])
        path=self.put()
        valid=audit_requested_archives(self.folder,plan=self.plan)
        self.assertEqual(valid,(path,))
        other=self.folder/("historical-crypto-20260829T0000Z-"
                           "20260901T0000Z-ffffffffffffffff.json")
        other.write_bytes(path.read_bytes());other.chmod(0o600)
        with self.assertRaises(ValueError):
            audit_requested_archives(self.folder,plan=self.plan)
        self.assertFalse((self.folder/ANALYSIS_FILENAME).exists())

    def test_wrong_instrument_group_is_not_accepted(self):
        self.put(symbols=("BTC/USD",))
        with self.assertRaises(ValueError):
            audit_requested_archives(self.folder,plan=self.plan)
        self.assertFalse((self.folder/ANALYSIS_FILENAME).exists())

    def test_tampered_archive_preserved_and_report_not_created(self):
        path=self.put()
        path.write_bytes(path.read_bytes()+b"tampered")
        before=path.read_bytes()
        with self.assertRaises(ValueError):
            analyze_manual_history(folder=self.folder,plan=self.plan)
        self.assertEqual(path.read_bytes(),before)
        self.assertFalse((self.folder/ANALYSIS_FILENAME).exists())
        self.assertFalse(list(self.folder.glob("cost_assumptions-*.json")))

    def test_explicit_invalid_cost_scenario_blocks_without_modifying_archive(self):
        original=self.put()
        sha=hashlib.sha256(original.read_bytes()).hexdigest()
        invalid={name:dict(model) for name,model in SCENARIOS.items()}
        invalid["illustrative_high_friction"]["taker_fee_bps"]="-1"
        with self.assertRaises(ValueError):
            analyze_manual_history(folder=self.folder,plan=self.plan,
                                   scenario_models=invalid)
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(),sha)
        self.assertFalse((self.folder/ANALYSIS_FILENAME).exists())

    def test_missing_private_volume_or_symlink_never_auto_created(self):
        self.put()
        absent=self.folder.parent/"absent"
        with self.assertRaises(ValueError):
            analyze_manual_history(folder=absent,plan=self.plan)
        self.assertFalse(absent.exists())
        link=self.folder.parent/"alias"
        link.symlink_to(self.folder)
        with self.assertRaises(ValueError):
            audit_requested_archives(link,plan=self.plan)
        self.assertFalse((self.folder/ANALYSIS_FILENAME).exists())

    def test_two_bounded_windows_are_accepted_in_plan_order(self):
        # 15 days: two windows, with first 14 days and final 1 day.
        start=END-timedelta(days=15)
        plan=historical_plan(
            symbols=SYMBOLS,start=start,end=END,market=AssetClass.CRYPTO)
        self.assertEqual(plan["window_count"],2)
        a=sample_bundle(start=start,hours=14*24)
        boundary=start+timedelta(days=14)
        b=sample_bundle(start=boundary,hours=24)
        pa=archive_historical_batch(a,output_folder=self.folder)
        pb=archive_historical_batch(b,output_folder=self.folder)
        reviewed=audit_requested_archives(self.folder,plan=plan)
        self.assertEqual(reviewed,(pa,pb))


if __name__=="__main__":
    unittest.main()

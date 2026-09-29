"""No-credential/network synthetic stock session workflow acceptance tests."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from signal_vault.ci_historical_equities import (
    SYMBOLS,APPROVAL,resolve_manual_equity_plan,
    execute_manual_equity_history,
)
from signal_vault.multi_asset_historical import HistoricalDataBatch
from signal_vault.research_universe import ResearchBar

NOW=datetime(2026,9,29,21,tzinfo=timezone.utc)
ENV={
    "GITHUB_ACTIONS":"true",
    "GITHUB_EVENT_NAME":"workflow_dispatch",
    "GITHUB_REPOSITORY":"Nkreddy15/signal-vault",
    "GITHUB_REF":"refs/heads/main",
    "SIGNAL_VAULT_EQUITY_READ_APPROVED":APPROVAL,
    "SIGNAL_VAULT_EQUITY_START_DATE":"2026-09-14",
    "SIGNAL_VAULT_EQUITY_END_DATE_EXCLUSIVE":"2026-09-26",
    "SIGNAL_VAULT_EQUITY_SYMBOLS":"AAPL AMD MSFT NVDA QQQ SPY",
    "SIGNAL_VAULT_EQUITY_FEED":"iex",
    "SIGNAL_VAULT_RESEARCH_DATA_KEY_ID":"FIXTURE_NEVER_REAL_KEY",
    "SIGNAL_VAULT_RESEARCH_DATA_SECRET":"FIXTURE_NEVER_REAL_SECRET",
}


class FakeLiquidIEXProvider:
    instances=[]
    drop_session=None
    def __init__(self,key,secret):
        self.key,self.secret=key,secret
        self.calls=[]
        self.instances.append(self)

    def fetch(self,*,specs,start,end,as_of,equity_feed,equity_expected_open_minutes):
        self.calls.append((start,end,equity_feed,tuple(x.symbol for x in specs)))
        n=len(self.calls)
        rows={}
        for symbol_index,spec in enumerate(specs):
            grid=tuple(equity_expected_open_minutes[spec.symbol])
            if (self.drop_session==n and spec.symbol=="SPY"):
                grid=grid[:-1]  # missing IEX hourly print must reject, not interpolate
            px=Decimal(100+symbol_index*10)
            rows[spec.symbol]=tuple(ResearchBar(
                spec.symbol,t,px,px+Decimal("1"),px-Decimal("1"),
                px,Decimal("15"),"alpaca_equity_iex|adjustment=all",
                as_of,False)
                for t in grid)
        return HistoricalDataBatch(
            "us_equity",tuple(x.symbol for x in specs),
            "alpaca_equity_iex","all",start.isoformat(),end.isoformat(),
            as_of.isoformat(),1,rows)


class ManualStockIEXWorkflowTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)/"private-equity-artifacts"
        FakeLiquidIEXProvider.instances=[]
        FakeLiquidIEXProvider.drop_session=None

    def test_dry_run_is_ten_actual_sessions_and_sixty_hours_per_symbol(self):
        plan=resolve_manual_equity_plan(env=ENV,as_of=NOW)
        self.assertEqual(plan["kind"],"OFFLINE_MANUAL_XNYS_CORE_HOURLY_IEX_DATA_ONLY_PLAN")
        self.assertEqual(plan["symbols"],list(SYMBOLS))
        self.assertEqual(plan["session_count"],10)
        self.assertEqual(plan["expected_complete_core_hours_per_symbol"],60)
        self.assertEqual(plan["credentials_accessed"],"NONE")
        self.assertEqual(plan["network_requests"],0)
        self.assertEqual(plan["feed"],"iex")
        self.assertTrue(plan["preopen_0930_to_1000_intentionally_omitted"])
        self.assertEqual(plan["sessions"][0]["minutes_excluded_after_open"],30)
        self.assertNotIn("FIXTURE_NEVER_REAL",json.dumps(plan))

    def test_full_six_stock_ten_session_history_and_cost_scenarios(self):
        result=execute_manual_equity_history(
            env=ENV,as_of=NOW,provider_factory=FakeLiquidIEXProvider,
            output_folder=self.root)
        self.assertEqual(result["completed_exchange_sessions"],10)
        self.assertEqual(result["historical_bars_per_asset"],60)
        self.assertEqual(result["archive_count"],10)
        self.assertEqual(result["prospective_observations_verified"],0)
        self.assertEqual(result["broker_order_submission"],"DISABLED")
        self.assertEqual(len(FakeLiquidIEXProvider.instances),1)
        provider=FakeLiquidIEXProvider.instances[0]
        self.assertEqual(len(provider.calls),10)
        self.assertEqual(provider.calls[0][:3],(
            datetime(2026,9,14,14,tzinfo=timezone.utc),
            datetime(2026,9,14,20,tzinfo=timezone.utc),"iex"))
        self.assertTrue(all(call[2]=="iex" and call[3]==SYMBOLS
                            for call in provider.calls))
        report_path=self.root/"offline_equity_research.json"
        raw=report_path.read_bytes()
        self.assertEqual(report_path.stat().st_mode &0o777,0o600)
        self.assertEqual(result["report_sha256"],hashlib.sha256(raw).hexdigest())
        self.assertNotIn(b"FIXTURE_NEVER_REAL",raw)
        body=json.loads(raw)
        self.assertTrue(body["regular_opening_partial_bucket_omitted"])
        self.assertTrue(body["sparse_IEX_data_cannot_be_auto_filled"])
        self.assertTrue(body["historical_no_prospective_forward_observations"])
        self.assertEqual(body["broker_order_submission"],"DISABLED")
        self.assertEqual(len(body["source_sha256"]),10)
        self.assertEqual(
            set(body["three_estimated_cost_scenarios"]),
            {"illustrative_low_equity_friction",
             "illustrative_base_equity_friction",
             "illustrative_high_equity_friction"})
        self.assertEqual(
            body["quality_reviews"]["AAPL"]["feed"],
            "alpaca_equity_iex|adjustment=all")
        self.assertTrue(all(r["bar_count"]==60 for r in body["quality_reviews"].values()))
        for scenario in body["three_estimated_cost_scenarios"].values():
            book=scenario["offline_report"][
                "all_predeclared_shared_bankroll_research_books"]
            self.assertEqual(len(book),4)
            self.assertEqual(book["cash-v1-predeclared"]["initial_bankroll_usd"],"100")
            self.assertEqual(
                scenario["offline_report"]["broker_order_submission"],"DISABLED")
        with self.assertRaises(ValueError):
            execute_manual_equity_history(
                env=ENV,as_of=NOW,provider_factory=FakeLiquidIEXProvider,
                output_folder=self.root)

    def test_missing_one_IEX_hour_rejected_without_fabricated_completed_report(self):
        FakeLiquidIEXProvider.drop_session=3
        with self.assertRaises(ValueError):
            execute_manual_equity_history(
                env=ENV,as_of=NOW,provider_factory=FakeLiquidIEXProvider,
                output_folder=self.root)
        self.assertFalse((self.root/"offline_equity_research.json").exists())
        self.assertEqual(
            len(list(self.root.glob("historical-us_equity-*.json"))),2)

    def test_wrong_branch_trigger_feed_symbols_and_unclosed_day_gate_before_keys(self):
        for mod in (
            {"GITHUB_EVENT_NAME":"pull_request"},
            {"GITHUB_REF":"refs/heads/other"},
            {"SIGNAL_VAULT_EQUITY_FEED":"sip"},
            {"SIGNAL_VAULT_EQUITY_SYMBOLS":"AAPL AMD MSFT NVDA SPY"},
            {"SIGNAL_VAULT_EQUITY_READ_APPROVED":"PAPER_BUY"},
            {"ALPACA_LIVE_KEY_ID":"FORBIDDEN"},
        ):
            with self.subTest(mod=mod),self.assertRaises((ValueError,PermissionError)):
                resolve_manual_equity_plan(env={**ENV,**mod},as_of=NOW)
        with self.assertRaises(ValueError):
            resolve_manual_equity_plan(
                env=ENV,as_of=datetime(2026,9,25,15,tzinfo=timezone.utc))
        with self.assertRaises(PermissionError):
            execute_manual_equity_history(
                env={k:v for k,v in ENV.items()
                     if k!="SIGNAL_VAULT_RESEARCH_DATA_SECRET"},
                as_of=NOW,provider_factory=lambda *args:self.fail("no keys"),
                output_folder=self.root)
        self.assertFalse(self.root.exists())


if __name__=="__main__":
    unittest.main()

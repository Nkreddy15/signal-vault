"""CLI boundary: dry-run cannot access credentials/network or orders."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from signal_vault.multi_asset_historical import HistoricalDataBatch,archive_historical_batch
from signal_vault.multi_asset_research_cli import (
    configured_costs,download_history,explicit_equity_bar_grid,
    historical_plan,main,run_offline_report,windows,
)
from signal_vault.research_universe import AssetClass,ResearchBar

START=datetime(2026,9,29,17,tzinfo=timezone.utc)
END=START+timedelta(hours=2)
NOW=END+timedelta(minutes=7)
HOUR=timedelta(hours=1)


def rows(symbol, start, n=70):
    return tuple(
        ResearchBar(symbol,start+i*HOUR,Decimal("100"),
                    Decimal("101"),Decimal("99"),Decimal("100"),
                    Decimal("20"),"alpaca_crypto_us",
                    NOW,False)
        for i in range(n)
    )


class FakeProvider:
    def __init__(self,key,secret):
        self.key=key
        self.secret=secret
        self.calls=[]

    def fetch(self,*,specs,start,end,as_of,equity_feed,equity_expected_open_minutes):
        self.calls.append((tuple(x.symbol for x in specs),start,end))
        return HistoricalDataBatch(
            "crypto",tuple(sorted(x.symbol for x in specs)),
            "alpaca_crypto_us","not_applicable",start.isoformat(),end.isoformat(),
            as_of.isoformat(),1,{
                x.symbol:rows(x.symbol,start,int((end-start)/HOUR))
                for x in specs})


class CLIResearchTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.private=self.root/"private-data"
        self.private.mkdir(mode=0o700)

    def test_dry_run_no_getpass_or_provider_or_credentials(self):
        result=historical_plan(
            symbols=("ETH/USD","BTC/USD"),start=START,end=END,
            market=AssetClass.CRYPTO)
        self.assertEqual(result["window_count"],1)
        self.assertEqual(result["requests_triggered"],0)
        self.assertEqual(result["credential_access"],"NONE")
        stream=io.StringIO()
        with patch("signal_vault.multi_asset_research_cli.getpass.getpass",
                   side_effect=AssertionError("dry-run must never read keys")),redirect_stdout(stream):
            code=main([
                "--dry-run","--market","crypto","--symbols","BTC/USD","ETH/USD",
                "--start",START.isoformat(),"--end",END.isoformat()])
        self.assertEqual(code,0)
        printed=json.loads(stream.getvalue())
        self.assertEqual(printed["broker_order_submission"],"DISABLED")
        self.assertEqual(printed["requests_triggered"],0)
        self.assertNotIn("FAKE_DATA",stream.getvalue())

    def test_bounded_split_for_months_instead_of_one_unbounded_call(self):
        plans=windows(START,START+timedelta(days=41))
        self.assertEqual(len(plans),3)
        self.assertEqual(plans[0][1],START+timedelta(days=14))
        self.assertEqual(plans[-1][1],START+timedelta(days=41))
        with self.assertRaises(ValueError):
            windows(START,START+timedelta(days=421))

    def test_prompted_data_get_archives_only_retrospective_fake_pages(self):
        fake=[]
        def factory(k,s):
            obj=FakeProvider(k,s)
            fake.append(obj)
            return obj
        result=download_history(
            symbols=("BTC/USD","ETH/USD"),start=START,end=END,
            market=AssetClass.CRYPTO,equity_feed=None,
            output_folder=self.private,key_id="PRIVATE_KEY_SENTINEL",
            secret="PRIVATE_SECRET_SENTINEL",provider_factory=factory,
            now=NOW)
        self.assertEqual(result["completed_history_windows"],1)
        self.assertEqual(len(fake[0].calls),1)
        self.assertNotIn("PRIVATE_KEY_SENTINEL",json.dumps(result))
        self.assertNotIn("PRIVATE_SECRET_SENTINEL",json.dumps(result))
        self.assertTrue(result["credential_values_in_output"] is False)
        self.assertEqual(result["results"][0]["prospective_observations_verified"],0)
        saved=self.private/result["results"][0]["archive_basename"]
        self.assertTrue(saved.is_file())
        self.assertNotIn("PRIVATE_SECRET_SENTINEL",saved.read_text())
        self.assertEqual(saved.stat().st_mode & 0o777,0o600)

    def test_history_report_requires_private_cost_file_and_no_api(self):
        start=START-70*HOUR
        archive=HistoricalDataBatch(
            "crypto",("BTC/USD",),"alpaca_crypto_us","not_applicable",
            start.isoformat(),START.isoformat(),NOW.isoformat(),1,
            {"BTC/USD":rows("BTC/USD",start)})
        path=archive_historical_batch(archive,output_folder=self.private)
        cfg=self.private/"costs.json"
        cfg.write_text(json.dumps({
            "BTC/USD":{
                "taker_fee_bps":"25",
                "full_spread_bps":"4",
                "slippage_per_side_bps":"10",
            }}))
        cfg.chmod(0o600)
        costs=configured_costs(cfg,symbols=("BTC/USD",))
        self.assertEqual(costs["BTC/USD"].taker_fee_bps,Decimal("25"))
        result=run_offline_report((path,),cost_config=cfg)
        self.assertEqual(result["network_requests"],"NONE")
        self.assertEqual(result["credential_access"],"NONE")
        self.assertEqual(result["one_shared_portfolio_baseline"]["broker_order_submission"],
                         "DISABLED")
        self.assertEqual(result["per_symbol_quality_reviews"]["BTC/USD"]["historical_bars"],70)
        cfg.chmod(0o644)
        with self.assertRaises(ValueError):
            run_offline_report((path,),cost_config=cfg)

    def test_equity_grid_requires_explicit_review_flag_and_feed(self):
        path=self.private/"grid.json"
        data={
            "kind":"OPERATOR_REVIEWED_EQUITY_HOURLY_BAR_GRID",
            "feed":"iex","reviewed_provider_timestamps":True,
            "symbols":{"SPY":[START.isoformat(),(START+HOUR).isoformat()]},
        }
        path.write_text(json.dumps(data));path.chmod(0o600)
        out=explicit_equity_bar_grid(path,symbols=("SPY",),feed="iex")
        self.assertEqual(out["SPY"],(START,START+HOUR))
        with self.assertRaises(ValueError):
            explicit_equity_bar_grid(path,symbols=("SPY",),feed="sip")
        data["reviewed_provider_timestamps"]=False
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            explicit_equity_bar_grid(path,symbols=("SPY",),feed="iex")

    def test_download_never_runs_on_future_window_or_public_folder(self):
        with self.assertRaises(ValueError):
            download_history(
                symbols=("BTC/USD",),start=START,end=END,
                market=AssetClass.CRYPTO,equity_feed=None,
                output_folder=self.private,key_id="K",secret="S",
                provider_factory=lambda *args: self.fail("no GET permitted"),
                now=START)
        self.private.chmod(0o755)
        with self.assertRaises(ValueError):
            download_history(
                symbols=("BTC/USD",),start=START,end=END,
                market=AssetClass.CRYPTO,equity_feed=None,
                output_folder=self.private,key_id="K",secret="S",
                provider_factory=lambda *args: self.fail("no GET permitted"),
                now=NOW)


if __name__=="__main__":
    unittest.main()

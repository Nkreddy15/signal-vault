"""Synthetic end-to-end historical batch -> archive -> SHA -> research pipeline."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.multi_asset_historical import (
    HistoricalDataBatch,archive_historical_batch,
)
from signal_vault.multi_asset_simulation import ExplicitRoundTripCosts,HYPOTHESES
from signal_vault.offline_multimarket_pipeline import (
    combine_historical_archives,describe_multi_asset_research,
    read_historical_archive,
)
from signal_vault.research_universe import ResearchBar

HOUR=timedelta(hours=1)
END=datetime(2026,9,29,19,tzinfo=timezone.utc)
AS_OF=END+timedelta(minutes=7)
COST=ExplicitRoundTripCosts(Decimal("25"),Decimal("4"),Decimal("10"))


def bars(sym,start,count,*,feed="alpaca_crypto_us",captured=AS_OF):
    return tuple(
        ResearchBar(
            sym,start+i*HOUR,Decimal("100")+Decimal(i),
            Decimal("102")+Decimal(i),Decimal("99")+Decimal(i),
            Decimal("101")+Decimal(i),Decimal("6"),feed,captured,False)
        for i in range(count)
    )


def batch_crypto(dataset,*,captured=AS_OF,first=None,end=None,feed="alpaca_crypto_us"):
    names=tuple(sorted(dataset))
    start=min(items[0].start_utc for items in dataset.values()) if first is None else first
    stop=max(items[-1].closed_utc for items in dataset.values()) if end is None else end
    return HistoricalDataBatch(
        "crypto",names,feed,"not_applicable",
        start.isoformat(),stop.isoformat(),captured.isoformat(),1,dataset)


class OfflinePipelineTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)/"private-history"
        self.root.mkdir(mode=0o700)

    def test_hist_archive_sha_roundtrip_and_two_asset_offline_report(self):
        a=bars("BTC/USD",END-70*HOUR,70)
        b=bars("ETH/USD",END-70*HOUR,70)
        before=batch_crypto({"BTC/USD":a,"ETH/USD":b})
        path=archive_historical_batch(before,output_folder=self.root)
        restored=read_historical_archive(path)
        self.assertEqual(restored.canonical_bytes(),before.canonical_bytes())
        combined,qa=combine_historical_archives((restored,),as_of=AS_OF)
        self.assertEqual(set(combined),{"BTC/USD","ETH/USD"})
        self.assertEqual(qa["BTC/USD"]["historical_bars"],70)
        self.assertEqual(qa["ETH/USD"]["prospective_bars"],0)
        report=describe_multi_asset_research(
            combined,as_of=AS_OF,
            costs={"BTC/USD":COST,"ETH/USD":COST})
        self.assertEqual(len(report["assets"]),2)
        self.assertEqual(len(report["predeclared_hypotheses"]),4)
        self.assertEqual(report["one_shared_portfolio_baseline"]["initial_bankroll_usd"],"100")
        self.assertEqual(len(report["all_predeclared_shared_bankroll_research_books"]),4)
        self.assertFalse(report["portfolio_hypothesis_selection_performed"])
        self.assertEqual(
            report["all_predeclared_shared_bankroll_research_books"]
                  ["cash-v1-predeclared"]["final_marked_equity_usd"],"100")
        self.assertEqual(report["broker_order_submission"],"DISABLED")
        self.assertTrue(report["research_only_historical"])
        for asset in report["assets"]:
            self.assertEqual(len(report["per_asset_chronological_folds"][asset]),4)
            for h in HYPOTHESES:
                self.assertEqual(
                    set(report["per_asset_chronological_folds"][asset][h.name]),
                    {"development","validation","untouched_test"})

    def test_archive_refuses_renamed_or_modified_source_and_symlink(self):
        before=batch_crypto({"BTC/USD":bars("BTC/USD",END-70*HOUR,70)})
        path=archive_historical_batch(before,output_folder=self.root)
        newpath=self.root/("historical-crypto-20260926T2100Z-"
                           "20260929T1900Z-0000000000000000.json")
        newpath.write_bytes(path.read_bytes())
        newpath.chmod(0o600)
        with self.assertRaises(ValueError):
            read_historical_archive(newpath)
        link=self.root/"link"
        link.symlink_to(path)
        with self.assertRaises(ValueError):
            read_historical_archive(link)
        path.write_bytes(path.read_bytes()+b"tamper")
        with self.assertRaises(ValueError):
            read_historical_archive(path)

    def test_nonoverlap_segment_joins_and_gap_detection(self):
        start=END-70*HOUR
        a=bars("BTC/USD",start,35)
        b=bars("BTC/USD",start+35*HOUR,35)
        one=batch_crypto({"BTC/USD":a},captured=AS_OF)
        two=batch_crypto({"BTC/USD":b},captured=AS_OF)
        comb,_=combine_historical_archives((two,one),as_of=AS_OF)
        self.assertEqual(len(comb["BTC/USD"]),70)
        missing=batch_crypto({"BTC/USD":bars("BTC/USD",start+36*HOUR,34)},
                             captured=AS_OF)
        with self.assertRaises(ValueError):
            combine_historical_archives((one,missing),as_of=AS_OF)
        with self.assertRaises(ValueError):
            combine_historical_archives((one,one),as_of=AS_OF)

    def test_mixed_feed_cannot_be_spliced_into_a_single_asset_history(self):
        start=END-70*HOUR
        one=batch_crypto({"BTC/USD":bars("BTC/USD",start,35)})
        two=batch_crypto(
            {"BTC/USD":bars("BTC/USD",start+35*HOUR,35,feed="different_feed")},
            feed="different_feed")
        with self.assertRaises(ValueError):
            combine_historical_archives((one,two),as_of=AS_OF)

    def test_equity_requires_explicit_calendar_in_join_and_comparison(self):
        days=[0,1,2,3,4,7,8,9,10,11]
        timeline=tuple(
            datetime(2026,9,14,13,30,tzinfo=timezone.utc)
            +timedelta(days=d,hours=h)
            for d in days for h in range(6))
        last=timeline[-1]+HOUR
        captured=last+timedelta(minutes=7)
        rows=tuple(
            ResearchBar("SPY",t,Decimal("100"),Decimal("101"),
                        Decimal("99"),Decimal("100"),Decimal("1"),
                        "alpaca_equity_iex|adjustment=all",captured,False)
            for t in timeline)
        bundle=HistoricalDataBatch(
            "us_equity",("SPY",),"alpaca_equity_iex","all",
            timeline[0].isoformat(),last.isoformat(),
            captured.isoformat(),1,{"SPY":rows})
        path=archive_historical_batch(bundle,output_folder=self.root)
        restored=read_historical_archive(path)
        with self.assertRaises(ValueError):
            combine_historical_archives((restored,),as_of=captured)
        combined,reviews=combine_historical_archives(
            (restored,),as_of=captured,equity_calendars={"SPY":timeline})
        self.assertEqual(reviews["SPY"]["asset_class"],"us_equity")
        report=describe_multi_asset_research(
            combined,as_of=captured,costs={"SPY":COST},
            equity_calendars={"SPY":timeline})
        self.assertEqual(report["assets"],["SPY"])
        self.assertEqual(report["broker_order_submission"],"DISABLED")

    def test_different_symbol_costs_are_required(self):
        seq={"BTC/USD":bars("BTC/USD",END-70*HOUR,70),
             "ETH/USD":bars("ETH/USD",END-70*HOUR,70)}
        with self.assertRaises(ValueError):
            describe_multi_asset_research(
                seq,as_of=AS_OF,costs={"BTC/USD":COST})


if __name__=="__main__":
    unittest.main()

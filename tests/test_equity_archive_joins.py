"""Separate equity-session SHA archive joins, NOT 24/7 crypto backfill."""
from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import date,datetime,timedelta,timezone
from decimal import Decimal

from signal_vault.equity_session_grid import conservative_core_hour_plan
from signal_vault.multi_asset_historical import HistoricalDataBatch
from signal_vault.offline_multimarket_pipeline import combine_historical_archives
from signal_vault.research_universe import ResearchBar

AS_OF=datetime(2026,10,1,tzinfo=timezone.utc)
HOUR=timedelta(hours=1)


def equity_batch(spec, captured=AS_OF):
    points=spec.expected_opens
    return HistoricalDataBatch(
        "us_equity",("SPY",),"alpaca_equity_iex","all",
        spec.query_start.isoformat(),spec.query_end.isoformat(),
        captured.isoformat(),1,{
            "SPY":tuple(ResearchBar(
                "SPY",t,Decimal("100"),Decimal("101"),Decimal("99"),
                Decimal("100"),Decimal("100"),
                "alpaca_equity_iex|adjustment=all",captured,False)
                for t in points)
        })


class StockHistoryJoinsTests(unittest.TestCase):
    def setUp(self):
        self.sessions=conservative_core_hour_plan(
            start_date=date(2026,9,14),end_date_exclusive=date(2026,9,17),
            as_of=AS_OF)
        self.assertEqual(len(self.sessions),3)
        self.archive=tuple(equity_batch(s) for s in self.sessions)
        self.full_grid=tuple(t for s in self.sessions for t in s.expected_opens)

    def test_two_overnight_gaps_allowed_only_for_exact_exchange_grid(self):
        rows,reviews=combine_historical_archives(
            self.archive[::-1],as_of=AS_OF,
            equity_calendars={"SPY":self.full_grid})
        self.assertEqual(len(rows["SPY"]),18)
        self.assertEqual(reviews["SPY"]["asset_class"],"us_equity")
        self.assertEqual(reviews["SPY"]["historical_bars"],18)
        self.assertEqual(reviews["SPY"]["prospective_bars"],0)
        self.assertEqual(rows["SPY"][5].closed_utc,self.sessions[0].query_end)
        self.assertEqual(rows["SPY"][6].start_utc,self.sessions[1].query_start)
        self.assertGreater(rows["SPY"][6].start_utc-rows["SPY"][5].closed_utc,
                           timedelta(hours=12))

    def test_missing_session_or_fabricated_afterhours_rejected(self):
        with self.assertRaises(ValueError):
            combine_historical_archives(
                self.archive[:2],as_of=AS_OF,
                equity_calendars={"SPY":self.full_grid})
        with self.assertRaises(ValueError):
            combine_historical_archives(self.archive,as_of=AS_OF)
        b0=self.archive[0]
        bad=replace(
            b0,bars={"SPY":b0.bars["SPY"]+(
                replace(b0.bars["SPY"][-1],
                        start_utc=b0.bars["SPY"][-1].start_utc+HOUR),)})
        with self.assertRaises(ValueError):
            combine_historical_archives(
                (bad,)+self.archive[1:],as_of=AS_OF,
                equity_calendars={"SPY":self.full_grid})

    def test_overlapping_equity_archive_is_rejected_even_when_calendar_supplied(self):
        with self.assertRaises(ValueError):
            combine_historical_archives(
                (self.archive[0],self.archive[0],self.archive[1]),
                as_of=AS_OF,equity_calendars={
                    "SPY":self.full_grid[:12]})

    def test_early_close_session_uses_three_full_buckets(self):
        early=conservative_core_hour_plan(
            start_date=date(2026,11,27),
            end_date_exclusive=date(2026,11,28),
            as_of=datetime(2026,12,1,tzinfo=timezone.utc))[0]
        batch=equity_batch(early,captured=datetime(2026,12,1,tzinfo=timezone.utc))
        rows,reviews=combine_historical_archives(
            (batch,),as_of=AS_OF+timedelta(days=70),
            equity_calendars={"SPY":early.expected_opens})
        self.assertEqual(len(rows["SPY"]),3)
        self.assertEqual(rows["SPY"][-1].closed_utc,early.query_end)


if __name__=="__main__":
    unittest.main()

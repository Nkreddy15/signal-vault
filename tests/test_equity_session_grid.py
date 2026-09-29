"""Offline XNYS core-only stock hourly grid: DST, holidays, early close."""
from __future__ import annotations

import unittest
from datetime import date,datetime,timedelta,timezone

from signal_vault.equity_session_grid import conservative_core_hour_plan

UTC=timezone.utc
AS_OF=datetime(2026,12,31,23,tzinfo=UTC)


class ConservativeCoreXNYSCalendarTests(unittest.TestCase):
    def plan(self,a,b):
        return conservative_core_hour_plan(
            start_date=date.fromisoformat(a),
            end_date_exclusive=date.fromisoformat(b),as_of=AS_OF)

    def test_september_regular_session_omits_first_partial_premarket_bucket(self):
        days=self.plan("2026-09-14","2026-09-26")
        self.assertEqual(len(days),10)
        self.assertTrue(all(len(x.expected_opens)==6 for x in days))
        self.assertTrue(all(x.minutes_excluded_after_open==30 for x in days))
        first=days[0]
        self.assertEqual(first.trading_date,"2026-09-14")
        self.assertEqual(first.exchange_open_utc,"2026-09-14T13:30:00+00:00")
        self.assertEqual(first.query_start,datetime(2026,9,14,14,tzinfo=UTC))
        self.assertEqual(first.query_end,datetime(2026,9,14,20,tzinfo=UTC))
        self.assertEqual(
            first.expected_opens,
            tuple(datetime(2026,9,14,h,tzinfo=UTC) for h in (14,15,16,17,18,19)))
        self.assertEqual(first.minutes_excluded_before_close,0)
        self.assertNotIn(datetime(2026,9,14,13,tzinfo=UTC),first.expected_opens)
        self.assertEqual(first.as_dict()["extended_hours_excluded"],True)
        self.assertTrue(first.exchange_calendar_package_version)

    def test_november_dst_and_thanksgiving_halfday_are_not_24_7(self):
        result=self.plan("2026-11-23","2026-11-30")
        self.assertEqual([x.trading_date for x in result],
                         ["2026-11-23","2026-11-24","2026-11-25","2026-11-27"])
        early=result[-1]
        self.assertTrue(early.session_is_early_close)
        self.assertEqual(early.exchange_open_utc,"2026-11-27T14:30:00+00:00")
        self.assertEqual(early.exchange_close_utc,"2026-11-27T18:00:00+00:00")
        self.assertEqual(len(early.expected_opens),3)
        self.assertEqual(early.query_start,datetime(2026,11,27,15,tzinfo=UTC))
        self.assertEqual(early.query_end,datetime(2026,11,27,18,tzinfo=UTC))
        self.assertNotIn("2026-11-26",[x.trading_date for x in result])
        self.assertEqual(result[0].query_start.hour,15)  # US winter time

    def test_fourth_july_observed_holiday_and_nyse_core_clock(self):
        result=self.plan("2026-07-02","2026-07-07")
        self.assertEqual([x.trading_date for x in result],["2026-07-02","2026-07-06"])
        self.assertEqual(result[0].query_start.hour,14)

    def test_too_many_sessions_and_unclosed_calendar_fail_before_provider(self):
        with self.assertRaises(ValueError):
            self.plan("2026-07-01","2026-09-01")
        with self.assertRaises(ValueError):
            self.plan("2026-07-01","2026-07-01")
        with self.assertRaises(ValueError):
            conservative_core_hour_plan(
                start_date=date(2026,9,28),end_date_exclusive=date(2026,9,30),
                as_of=datetime(2026,9,29,15,tzinfo=UTC))
        with self.assertRaises(ValueError):
            conservative_core_hour_plan(
                start_date=date(2026,9,14),end_date_exclusive=date(2026,9,26),
                as_of=datetime(2026,9,27))  # missing UTC offset


if __name__=="__main__":
    unittest.main()

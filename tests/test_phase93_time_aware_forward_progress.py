import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from signal_vault.all_market_forward_status import (
    _equity_status,
    _kalshi_status,
)
from signal_vault.equity_cloud_sidecar import CHILD as EQUITY_CHILD
from signal_vault.equity_forward_collector import (
    archive_equity_forward_session_plan,
    precommit_equity_forward_session,
)
from signal_vault.kalshi_cloud_sidecar import CHILD as KALSHI_CHILD
from signal_vault.kalshi_prospective_collector import (
    archive_prospective_kalshi_plan,
    build_prospective_kalshi_plan,
)


UTC=timezone.utc
PLAN_TIME=datetime(2026,10,1,12,0,tzinfo=UTC)


def iso(value):
    return value.astimezone(UTC).isoformat().replace("+00:00","Z")


class FakeKalshiClient:
    def __init__(self):
        markets=[]
        for event_index in range(10):
            for leg in range(2):
                close=PLAN_TIME+timedelta(hours=30+event_index*3+leg)
                markets.append({
                    "ticker":f"MKT-{event_index:02d}-{leg}",
                    "event_ticker":f"EVT-{event_index:02d}",
                    "market_type":"binary",
                    "status":"open",
                    "close_time":iso(close),
                    "mve_collection_ticker":None,
                    "is_provisional":False,
                    "can_close_early":False,
                    "yes_bid_dollars":"0.40",
                    "yes_ask_dollars":"0.42",
                    "last_price_dollars":"0.41",
                })
        self.markets=markets

    def live_public_markets(self, *, status="open", limit=1000, cursor=None):
        return {"markets":[dict(x) for x in self.markets],"cursor":""}


class TimeAwareForwardProgressTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)/"forward"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)

    def test_equity_missing_future_hours_are_not_called_missed(self):
        child=self.root/EQUITY_CHILD
        child.mkdir(mode=0o700)
        child.chmod(0o700)
        plan=precommit_equity_forward_session(
            trading_date=date(2026,10,1),
            planned_at=PLAN_TIME,
        )
        archive_equity_forward_session_plan(plan,output_root=child)
        first=datetime.fromisoformat(plan["expected_core_opens_utc"][0])
        before=first
        status=_equity_status(self.root,as_of=before)
        self.assertEqual(status["decision_hours_missing_after_window"],0)
        self.assertEqual(
            status["decision_hours_not_due_yet"],
            plan["expected_core_hour_count"],
        )

        open_window=first+timedelta(hours=1,minutes=7)
        status=_equity_status(self.root,as_of=open_window)
        self.assertEqual(status["decision_hours_capture_window_open"],1)
        self.assertEqual(status["decision_hours_missing_after_window"],0)

        expired=first+timedelta(hours=1,minutes=31)
        status=_equity_status(self.root,as_of=expired)
        self.assertEqual(status["decision_hours_capture_window_open"],0)
        self.assertEqual(status["decision_hours_missing_after_window"],1)
        self.assertTrue(status["time_aware_progress_is_not_integrity_audit"])
        self.assertEqual(status["paper_order_submission"],"DISABLED")

    def test_kalshi_missing_future_snapshots_are_not_called_missed(self):
        child=self.root/KALSHI_CHILD
        child.mkdir(mode=0o700)
        child.chmod(0o700)
        plan=build_prospective_kalshi_plan(
            client=FakeKalshiClient(),
            planned_at=PLAN_TIME,
        )
        archive_prospective_kalshi_plan(plan,output_root=child)
        first_close=min(
            datetime.fromisoformat(x["close_time"])
            for x in plan["markets"]
        )
        earliest_target=first_close-timedelta(hours=24)

        before=_kalshi_status(
            self.root,
            as_of=earliest_target-timedelta(minutes=1),
        )
        self.assertEqual(before["decision_snapshots_missing_after_window"],0)
        self.assertEqual(before["decision_snapshot_windows_open"],0)
        self.assertGreater(before["decision_snapshots_not_due_yet"],0)

        open_window=_kalshi_status(
            self.root,
            as_of=earliest_target+timedelta(minutes=7),
        )
        self.assertGreaterEqual(open_window["decision_snapshot_windows_open"],1)
        self.assertEqual(open_window["decision_snapshots_missing_after_window"],0)

        expired=_kalshi_status(
            self.root,
            as_of=earliest_target+timedelta(minutes=61),
        )
        self.assertGreaterEqual(expired["decision_snapshots_missing_after_window"],1)
        self.assertTrue(expired["time_aware_progress_is_not_integrity_audit"])
        self.assertEqual(expired["demo_order_submission"],"DISABLED")
        self.assertEqual(expired["live_order_submission"],"DISABLED")

    def test_settlement_progress_distinguishes_not_due_from_pending(self):
        child=self.root/KALSHI_CHILD
        child.mkdir(mode=0o700)
        child.chmod(0o700)
        plan=build_prospective_kalshi_plan(
            client=FakeKalshiClient(),
            planned_at=PLAN_TIME,
        )
        archive_prospective_kalshi_plan(plan,output_root=child)
        closes=sorted(
            datetime.fromisoformat(x["close_time"])
            for x in plan["markets"]
        )
        before=_kalshi_status(
            self.root,
            as_of=closes[0]-timedelta(minutes=1),
        )
        self.assertEqual(before["settlements_pending_after_planned_close"],0)
        self.assertEqual(
            before["settlements_not_due_yet"],
            plan["planned_market_count"],
        )

        after=_kalshi_status(
            self.root,
            as_of=closes[0]+timedelta(minutes=1),
        )
        self.assertGreaterEqual(after["settlements_pending_after_planned_close"],1)
        self.assertLess(
            after["settlements_not_due_yet"],
            plan["planned_market_count"],
        )


if __name__=="__main__":
    unittest.main()

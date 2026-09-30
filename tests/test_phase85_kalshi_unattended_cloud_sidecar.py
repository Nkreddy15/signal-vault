import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from signal_vault.kalshi_cloud_sidecar import (
    ACTIVATION_ENV,
    ACTIVATION_VALUE,
    CHILD,
    ROOT_ENV,
    run_kalshi_sidecar_once,
)


UTC=timezone.utc
NOW=datetime(2026,10,1,12,0,tzinfo=UTC)


def iso(value):
    return value.astimezone(UTC).isoformat().replace("+00:00","Z")


class FakeClient:
    instances=[]

    def __init__(self):
        type(self).instances.append(self)
        self.market_calls=[]
        markets=[]
        for event_index in range(10):
            for leg in range(2):
                close=NOW+timedelta(hours=30+event_index*4+leg)
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
                    "result":"",
                    "settlement_ts":None,
                })
        self.markets={x["ticker"]:x for x in markets}

    def live_public_markets(self, *, status="open", limit=1000, cursor=None):
        return {"markets":[dict(x) for x in self.markets.values()],"cursor":""}

    def live_public_market(self,ticker):
        self.market_calls.append(ticker)
        return {"market":dict(self.markets[ticker])}


class KalshiCloudSidecarTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)/"forward"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        FakeClient.instances=[]

    def env(self,active=True):
        result={ROOT_ENV:str(self.root)}
        if active:
            result[ACTIVATION_ENV]=ACTIVATION_VALUE
        return result

    def test_inactive_sidecar_does_no_network_or_filesystem_work(self):
        result=run_kalshi_sidecar_once(
            env=self.env(active=False),
            now=NOW,
            client_factory=FakeClient,
        )
        self.assertEqual(result["status"],"INACTIVE")
        self.assertEqual(result["network_requests"],0)
        self.assertFalse(result["filesystem_writes"])
        self.assertEqual(FakeClient.instances,[])
        self.assertFalse((self.root/CHILD).exists())

    def test_first_active_tick_precommits_twenty_markets_without_credentials(self):
        result=run_kalshi_sidecar_once(
            env=self.env(),
            now=NOW,
            client_factory=FakeClient,
        )
        self.assertEqual(result["status"],"PRECOMMITTED_KALSHI_MARKET_PLAN")
        self.assertEqual(result["planned_market_count"],20)
        self.assertEqual(result["minimum_distinct_events"],10)
        self.assertEqual(result["credentials_accessed"],"NONE")
        self.assertEqual(result["demo_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")
        child=self.root/CHILD
        self.assertEqual(
            len(tuple(child.glob("kalshi-prospective-plan-*.json"))),1
        )
        self.assertEqual(child.stat().st_mode&0o077,0)

    def test_later_due_tick_captures_snapshot_without_order_permissions(self):
        first=run_kalshi_sidecar_once(
            env=self.env(),now=NOW,client_factory=FakeClient
        )
        client=FakeClient.instances[-1]
        # Sidecar constructs a fresh client each tick; find earliest close from
        # the fake universe and invoke just after its 24h target.
        earliest=min(
            datetime.fromisoformat(x["close_time"])
            for x in client.markets.values()
        )
        result=run_kalshi_sidecar_once(
            env=self.env(),
            now=earliest-timedelta(hours=24)+timedelta(minutes=7),
            client_factory=FakeClient,
        )
        self.assertEqual(result["status"],"COLLECTION_TICK_COMPLETE")
        self.assertGreaterEqual(result["prospective_snapshots_captured"],1)
        self.assertEqual(result["historical_backfill_count"],0)
        self.assertEqual(result["post_settlement_decision_count"],0)
        self.assertEqual(result["credentials_accessed"],"NONE")
        self.assertEqual(result["demo_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")
        child=self.root/CHILD
        self.assertGreaterEqual(
            len(tuple(child.glob("kalshi-forward-*-86400s.json"))),1
        )
        self.assertTrue(first["filesystem_writes"])

    def test_settlement_receipt_is_written_once_and_then_skipped(self):
        run_kalshi_sidecar_once(
            env=self.env(),now=NOW,client_factory=FakeClient
        )
        planning_client=FakeClient.instances[-1]
        earliest_ticker=min(
            planning_client.markets,
            key=lambda t:datetime.fromisoformat(
                planning_client.markets[t]["close_time"]
            ),
        )
        close=datetime.fromisoformat(
            planning_client.markets[earliest_ticker]["close_time"]
        )

        class SettledClient(FakeClient):
            def __init__(self):
                super().__init__()
                self.markets[earliest_ticker].update({
                    "status":"settled",
                    "result":"yes",
                    "settlement_ts":iso(close+timedelta(minutes=5)),
                })

        first=run_kalshi_sidecar_once(
            env=self.env(),
            now=close+timedelta(hours=1),
            client_factory=SettledClient,
        )
        child=self.root/CHILD
        receipt=child/f"kalshi-settlement-{earliest_ticker}.json"
        self.assertTrue(receipt.exists())
        before=receipt.read_bytes()
        second=run_kalshi_sidecar_once(
            env=self.env(),
            now=close+timedelta(hours=2),
            client_factory=SettledClient,
        )
        self.assertEqual(receipt.read_bytes(),before)
        self.assertGreaterEqual(second["settlements_pending"],0)
        self.assertEqual(first["demo_order_submission"],"DISABLED")

    def test_tampered_plan_blocks_all_future_collection(self):
        run_kalshi_sidecar_once(
            env=self.env(),now=NOW,client_factory=FakeClient
        )
        plan=next((self.root/CHILD).glob("kalshi-prospective-plan-*.json"))
        plan.write_text('{"kind":"tampered"}\n')
        plan.chmod(0o600)
        with self.assertRaises(ValueError):
            run_kalshi_sidecar_once(
                env=self.env(),
                now=NOW+timedelta(hours=1),
                client_factory=FakeClient,
            )


if __name__=="__main__":
    unittest.main()

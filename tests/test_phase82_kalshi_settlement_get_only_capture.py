import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from signal_vault.kalshi_prospective_collector import (
    archive_prospective_kalshi_plan,
    build_prospective_kalshi_plan,
    collect_due_kalshi_snapshots,
)
from signal_vault.kalshi_prospective_settlement import (
    collect_due_kalshi_settlements,
)


UTC=timezone.utc
NOW=datetime(2026,10,1,12,0,tzinfo=UTC)


def iso(value):
    return value.astimezone(UTC).isoformat().replace("+00:00","Z")


class FakeClient:
    def __init__(self):
        self.calls=[]
        markets=[]
        for event_index in range(10):
            for leg in range(2):
                close=NOW+timedelta(hours=30+event_index*2+leg)
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
        self.calls.append(ticker)
        return {"market":dict(self.markets[ticker])}


class KalshiProspectiveSettlementTests(unittest.TestCase):
    def make_root(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)/"kalshi"
        root.mkdir(mode=0o700)
        root.chmod(0o700)
        return root

    def build(self):
        client=FakeClient()
        plan=build_prospective_kalshi_plan(client=client,planned_at=NOW)
        root=self.make_root()
        archive_prospective_kalshi_plan(plan,output_root=root)
        return client,plan,root

    def test_unsettled_market_never_writes_outcome_receipt(self):
        client,plan,root=self.build()
        first=plan["markets"][0]
        close=datetime.fromisoformat(first["close_time"])
        result=collect_due_kalshi_settlements(
            plan=plan,
            now=close+timedelta(hours=1),
            output_root=root,
            client=client,
        )
        self.assertEqual(result["captured_count"],0)
        self.assertGreater(result["pending_count"],0)
        self.assertFalse(
            (root/f"kalshi-settlement-{first['ticker']}.json").exists()
        )
        self.assertEqual(result["post_settlement_decision_count"],0)
        self.assertEqual(result["demo_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")

    def test_settled_result_is_separate_from_earlier_decision_snapshot(self):
        client,plan,root=self.build()
        first=plan["markets"][0]
        close=datetime.fromisoformat(first["close_time"])

        collect_due_kalshi_snapshots(
            plan=plan,
            now=close-timedelta(hours=24)+timedelta(minutes=7),
            output_root=root,
            client=client,
        )
        snapshot=root/f"kalshi-forward-{first['ticker']}-86400s.json"
        before=snapshot.read_bytes()
        self.assertNotIn(b'"resolved_result"',before)
        self.assertNotIn(b'"result"',before)

        market=client.markets[first["ticker"]]
        market["status"]="settled"
        market["result"]="yes"
        market["settlement_ts"]=iso(close+timedelta(minutes=30))

        result=collect_due_kalshi_settlements(
            plan=plan,
            now=close+timedelta(hours=1),
            output_root=root,
            client=client,
        )
        receipt=root/f"kalshi-settlement-{first['ticker']}.json"
        self.assertTrue(receipt.exists())
        body=json.loads(receipt.read_text())
        self.assertEqual(body["resolved_result"],"yes")
        self.assertTrue(body["outcome_available_only_after_decision_stage"])
        self.assertFalse(body["earlier_decision_snapshot_rewritten"])
        self.assertFalse(body["post_settlement_decision_created"])
        self.assertEqual(snapshot.read_bytes(),before)
        self.assertEqual(result["post_settlement_decision_count"],0)

    def test_existing_settlement_receipt_is_idempotent_without_another_get(self):
        client,plan,root=self.build()
        first=plan["markets"][0]
        close=datetime.fromisoformat(first["close_time"])
        client.markets[first["ticker"]].update({
            "status":"settled",
            "result":"no",
            "settlement_ts":iso(close+timedelta(minutes=10)),
        })
        collect_due_kalshi_settlements(
            plan=plan,now=close+timedelta(hours=1),
            output_root=root,client=client,
        )
        calls_after_first=len(client.calls)
        result=collect_due_kalshi_settlements(
            plan=plan,now=close+timedelta(hours=2),
            output_root=root,client=client,
        )
        self.assertGreaterEqual(result["already_captured_count"],1)
        # Other due unsettled markets may still be checked, but the already
        # archived first ticker itself must not be looked up again.
        self.assertEqual(
            client.calls.count(first["ticker"]),
            1,
        )
        self.assertGreaterEqual(len(client.calls),calls_after_first)

    def test_future_settlement_timestamp_and_identity_drift_fail_closed(self):
        client,plan,root=self.build()
        first=plan["markets"][0]
        close=datetime.fromisoformat(first["close_time"])
        market=client.markets[first["ticker"]]
        market.update({
            "status":"settled",
            "result":"yes",
            "settlement_ts":iso(close+timedelta(hours=3)),
        })
        with self.assertRaises(ValueError):
            collect_due_kalshi_settlements(
                plan=plan,now=close+timedelta(hours=1),
                output_root=root,client=client,
            )

        client,plan,root=self.build()
        first=plan["markets"][0]
        close=datetime.fromisoformat(first["close_time"])
        market=client.markets[first["ticker"]]
        market.update({
            "status":"settled",
            "result":"yes",
            "event_ticker":"WRONG-EVENT",
            "settlement_ts":iso(close+timedelta(minutes=5)),
        })
        with self.assertRaises(ValueError):
            collect_due_kalshi_settlements(
                plan=plan,now=close+timedelta(hours=1),
                output_root=root,client=client,
            )


if __name__=="__main__":
    unittest.main()

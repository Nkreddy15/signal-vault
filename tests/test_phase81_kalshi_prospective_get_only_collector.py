import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from signal_vault.kalshi_prospective_collector import (
    HORIZONS,
    archive_prospective_kalshi_plan,
    build_prospective_kalshi_plan,
    collect_due_kalshi_snapshots,
    validate_prospective_kalshi_plan,
)


UTC=timezone.utc
NOW=datetime(2026,10,1,12,0,tzinfo=UTC)


def iso(value):
    return value.astimezone(UTC).isoformat().replace("+00:00","Z")


class FakeClient:
    def __init__(self, *, mutate_prices=False, close_early=False):
        self.mutate_prices=mutate_prices
        self.close_early=close_early
        self.single_calls=[]
        self.pages=[self._page()]

    def _page(self):
        markets=[]
        for event_index in range(12):
            for leg in range(2):
                close=NOW+timedelta(hours=30+event_index*3+leg)
                markets.append({
                    "ticker":f"MARKET-{event_index:02d}-{leg}",
                    "event_ticker":f"EVENT-{event_index:02d}",
                    "market_type":"binary",
                    "status":"open",
                    "open_time":iso(NOW-timedelta(days=2)),
                    "close_time":iso(close),
                    "mve_collection_ticker":None,
                    "is_provisional":False,
                    "can_close_early":bool(event_index%2),
                    "yes_bid_dollars":"0.99" if self.mutate_prices else "0.40",
                    "yes_ask_dollars":"1.00" if self.mutate_prices else "0.42",
                    "last_price_dollars":"0.01" if self.mutate_prices else "0.41",
                    "result":"yes" if self.mutate_prices else "no",
                })
        # Ineligible structural examples.
        markets.extend([
            {
                "ticker":"TOO-SOON","event_ticker":"EVENT-X",
                "market_type":"binary","status":"open",
                "close_time":iso(NOW+timedelta(hours=20)),
                "mve_collection_ticker":None,"is_provisional":False,
            },
            {
                "ticker":"MVE-X","event_ticker":"EVENT-Y",
                "market_type":"binary","status":"open",
                "close_time":iso(NOW+timedelta(days=2)),
                "mve_collection_ticker":"MVE-COLLECTION",
                "is_provisional":False,
            },
            {
                "ticker":"PROVISIONAL","event_ticker":"EVENT-Z",
                "market_type":"binary","status":"open",
                "close_time":iso(NOW+timedelta(days=2)),
                "mve_collection_ticker":None,"is_provisional":True,
            },
        ])
        return {"markets":markets,"cursor":""}

    def live_public_markets(self, *, status="open", limit=1000, cursor=None):
        self.assert_args=(status,limit,cursor)
        return self.pages[0]

    def live_public_market(self,ticker):
        self.single_calls.append(ticker)
        selected=next(
            x for x in self.pages[0]["markets"] if x.get("ticker")==ticker
        )
        market=dict(selected)
        if self.close_early:
            market["status"]="closed"
            market["result"]="yes"
        else:
            market["status"]="open"
            # Outcome field is intentionally present in the fake payload to
            # prove the prospective receipt does not persist it.
            market["result"]="yes"
        return {"market":market}


class KalshiProspectiveCollectorTests(unittest.TestCase):
    def make_root(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)/"kalshi-forward"
        root.mkdir(mode=0o700)
        root.chmod(0o700)
        return root

    def test_deterministic_plan_uses_structure_not_price_or_outcome(self):
        normal=build_prospective_kalshi_plan(
            client=FakeClient(mutate_prices=False),
            planned_at=NOW,
        )
        changed=build_prospective_kalshi_plan(
            client=FakeClient(mutate_prices=True),
            planned_at=NOW,
        )
        self.assertEqual(
            [x["ticker"] for x in normal["markets"]],
            [x["ticker"] for x in changed["markets"]],
        )
        self.assertEqual(normal["planned_market_count"],20)
        self.assertGreaterEqual(
            len({x["event_ticker"] for x in normal["markets"]}),10
        )
        self.assertFalse(normal["selection_uses_price"])
        self.assertFalse(normal["selection_uses_outcome_direction"])
        self.assertFalse(normal["selection_uses_historical_pnl"])
        self.assertEqual(normal["network_methods"],["GET"])
        self.assertEqual(normal["demo_order_submission"],"DISABLED")
        self.assertEqual(normal["live_order_submission"],"DISABLED")
        validate_prospective_kalshi_plan(normal)


    def test_paginated_discovery_can_continue_beyond_ten_pages_within_bound(self):
        class ElevenPageClient:
            def __init__(self):
                self.calls=0

            def live_public_markets(self, *, status="open", limit=1000, cursor=None):
                self.calls+=1
                index=0 if cursor is None else int(cursor)
                markets=[]
                for leg in range(2):
                    event_index=index
                    close=NOW+timedelta(hours=30+event_index*3+leg)
                    markets.append({
                        "ticker":f"PAGE-{index:02d}-{leg}",
                        "event_ticker":f"PAGEEVENT-{index:02d}",
                        "market_type":"binary",
                        "status":"active",
                        "close_time":iso(close),
                        "mve_collection_ticker":None,
                        "is_provisional":False,
                        "can_close_early":False,
                    })
                next_cursor="" if index==10 else str(index+1)
                return {"markets":markets,"cursor":next_cursor}

            def live_public_market(self,ticker):
                raise AssertionError("planning must not perform per-market quote GETs")

        client=ElevenPageClient()
        plan=build_prospective_kalshi_plan(
            client=client,
            planned_at=NOW,
            market_count=22,
        )
        self.assertEqual(plan["discovery_pages"],11)
        self.assertEqual(client.calls,11)
        self.assertEqual(plan["planned_market_count"],22)
        self.assertGreaterEqual(
            len({x["event_ticker"] for x in plan["markets"]}),10
        )
        self.assertEqual(plan["network_methods"],["GET"])
        self.assertEqual(plan["demo_order_submission"],"DISABLED")
        self.assertEqual(plan["live_order_submission"],"DISABLED")

    def test_plan_archive_is_private_create_only_and_tamper_detected(self):
        root=self.make_root()
        plan=build_prospective_kalshi_plan(
            client=FakeClient(),planned_at=NOW
        )
        path=archive_prospective_kalshi_plan(plan,output_root=root)
        self.assertEqual(path.stat().st_mode&0o077,0)
        before=path.read_bytes()
        self.assertEqual(
            archive_prospective_kalshi_plan(plan,output_root=root),path
        )
        self.assertEqual(path.read_bytes(),before)
        changed=dict(plan)
        changed["selection_uses_price"]=True
        with self.assertRaises(ValueError):
            validate_prospective_kalshi_plan(changed)

    def test_due_24h_snapshot_records_public_quote_but_never_result(self):
        root=self.make_root()
        client=FakeClient()
        plan=build_prospective_kalshi_plan(client=client,planned_at=NOW)
        archive_prospective_kalshi_plan(plan,output_root=root)
        first=plan["markets"][0]
        close=datetime.fromisoformat(first["close_time"])
        result=collect_due_kalshi_snapshots(
            plan=plan,
            now=close-timedelta(hours=24)+timedelta(minutes=7),
            output_root=root,
            client=client,
        )
        matching=[
            x for x in result["captured"]
            if x["ticker"]==first["ticker"] and
               x["horizon_seconds"]==86400
        ]
        self.assertEqual(len(matching),1)
        path=root/matching[0]["file"]
        receipt=json.loads(path.read_text())
        self.assertTrue(receipt["decision_valid"])
        self.assertEqual(receipt["yes_bid_dollars"],"0.40")
        self.assertEqual(receipt["yes_ask_dollars"],"0.42")
        self.assertEqual(receipt["last_price_dollars"],"0.41")
        self.assertFalse(receipt["outcome_direction_recorded"])
        self.assertFalse(receipt["result_field_recorded"])
        self.assertNotIn("result",receipt)
        self.assertEqual(receipt["demo_order_submission"],"DISABLED")
        self.assertEqual(receipt["live_order_submission"],"DISABLED")

    def test_early_closed_market_creates_invalid_snapshot_without_outcome_or_price(self):
        root=self.make_root()
        client=FakeClient(close_early=True)
        plan=build_prospective_kalshi_plan(client=client,planned_at=NOW)
        first=plan["markets"][0]
        close=datetime.fromisoformat(first["close_time"])
        result=collect_due_kalshi_snapshots(
            plan=plan,
            now=close-timedelta(hours=24)+timedelta(minutes=5),
            output_root=root,
            client=client,
        )
        matching=[
            x for x in result["captured"]
            if x["ticker"]==first["ticker"] and
               x["horizon_seconds"]==86400
        ]
        self.assertEqual(len(matching),1)
        receipt=json.loads((root/matching[0]["file"]).read_text())
        self.assertFalse(receipt["decision_valid"])
        self.assertIsNone(receipt["yes_bid_dollars"])
        self.assertIsNone(receipt["yes_ask_dollars"])
        self.assertIsNone(receipt["last_price_dollars"])
        self.assertNotIn("result",receipt)
        self.assertFalse(receipt["outcome_direction_recorded"])

    def test_missed_horizon_is_reported_and_never_backfilled(self):
        root=self.make_root()
        client=FakeClient()
        plan=build_prospective_kalshi_plan(client=client,planned_at=NOW)
        first=plan["markets"][0]
        close=datetime.fromisoformat(first["close_time"])
        result=collect_due_kalshi_snapshots(
            plan=plan,
            now=close-timedelta(hours=23),
            output_root=root,
            client=client,
        )
        missed=[
            x for x in result["missed"]
            if x["ticker"]==first["ticker"] and
               x["horizon_seconds"]==86400
        ]
        self.assertEqual(len(missed),1)
        self.assertEqual(
            missed[0]["reason"],
            "MISSED_PROSPECTIVE_CAPTURE_WINDOW_NO_BACKFILL",
        )
        self.assertEqual(result["historical_backfill_count"],0)
        self.assertEqual(result["post_settlement_decision_count"],0)

    def test_invalid_plan_or_too_few_events_fails_closed(self):
        class FewEvents(FakeClient):
            def _page(self):
                page=super()._page()
                for market in page["markets"]:
                    if market.get("market_type")=="binary":
                        market["event_ticker"]="EVENT-ONE"
                return page
        with self.assertRaises(ValueError):
            build_prospective_kalshi_plan(
                client=FewEvents(),planned_at=NOW
            )
        plan=build_prospective_kalshi_plan(
            client=FakeClient(),planned_at=NOW
        )
        plan["markets"][0]["reference_horizons_seconds"]=[21600]
        with self.assertRaises(ValueError):
            validate_prospective_kalshi_plan(plan)


if __name__=="__main__":
    unittest.main()

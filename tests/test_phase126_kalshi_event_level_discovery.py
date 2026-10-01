import unittest
from datetime import datetime, timedelta, timezone

from signal_vault.kalshi_prospective_collector import (
    PLAN_POLICY,
    build_prospective_kalshi_plan,
)


UTC=timezone.utc
NOW=datetime(2026,10,1,12,0,tzinfo=UTC)


def iso(value):
    return value.astimezone(UTC).isoformat().replace("+00:00","Z")


class EventDiscoveryClient:
    def __init__(self):
        self.calls=[]

    def live_public_events(
        self,*,status="open",limit=200,cursor=None,
        with_nested_markets=True,min_close_ts=None,
    ):
        self.calls.append({
            "status":status,
            "limit":limit,
            "cursor":cursor,
            "with_nested_markets":with_nested_markets,
            "min_close_ts":min_close_ts,
        })
        page_index=0 if cursor is None else int(cursor)
        start=0 if page_index==0 else 6
        count=6 if page_index==0 else 5
        events=[]
        for event_index in range(start,start+count):
            markets=[]
            for leg in range(2):
                close=NOW+timedelta(hours=30+event_index*2+leg)
                markets.append({
                    "ticker":f"EVMKT-{event_index:02d}-{leg}",
                    # Deliberately omit event_ticker from nested market; the
                    # event identity must be inherited structurally.
                    "market_type":"binary",
                    "status":"active",
                    "close_time":iso(close),
                    "mve_collection_ticker":None,
                    "is_provisional":False,
                    "can_close_early":False,
                    # Price/outcome-looking fields may be present but selection
                    # must not use or persist them.
                    "yes_bid_dollars":"0.01",
                    "yes_ask_dollars":"0.99",
                    "result":"yes",
                })
            events.append({
                "event_ticker":f"EVENT-{event_index:02d}",
                "markets":markets,
            })
        # Keep a non-empty cursor on page two. Planner must stop because the
        # predeclared 22-market / >=10-event sample is already satisfied.
        return {
            "events":events,
            "cursor":"1" if page_index==0 else "2",
        }

    def live_public_market(self,ticker):
        raise AssertionError("planning must not perform per-market quote GETs")


class KalshiEventLevelDiscoveryTests(unittest.TestCase):
    def test_event_pages_stop_when_predeclared_sample_is_satisfied(self):
        client=EventDiscoveryClient()
        plan=build_prospective_kalshi_plan(
            client=client,
            planned_at=NOW,
            market_count=22,
        )
        self.assertEqual(plan["policy_version"],PLAN_POLICY)
        self.assertEqual(plan["planned_market_count"],22)
        self.assertGreaterEqual(
            len({item["event_ticker"] for item in plan["markets"]}),10
        )
        self.assertEqual(plan["discovery_pages"],2)
        self.assertEqual(len(client.calls),2)
        self.assertEqual(
            plan["discovery_source"],
            "PUBLIC_EVENTS_WITH_NESTED_MARKETS",
        )
        self.assertTrue(
            plan["sample_target_reached_before_catalog_exhaustion"]
        )
        self.assertEqual(
            plan["sample_stop_rule"],
            "STOP_AFTER_AT_LEAST_REQUESTED_MARKETS_AND_TEN_DISTINCT_EVENTS",
        )
        self.assertFalse(plan["selection_uses_price"])
        self.assertFalse(plan["selection_uses_outcome_direction"])
        self.assertFalse(plan["selection_uses_historical_pnl"])
        self.assertEqual(plan["network_methods"],["GET"])
        self.assertEqual(plan["credentials_accessed"],"NONE")
        self.assertEqual(plan["demo_order_submission"],"DISABLED")
        self.assertEqual(plan["live_order_submission"],"DISABLED")
        self.assertTrue(all("result" not in item for item in plan["markets"]))
        self.assertTrue(all("yes_bid_dollars" not in item for item in plan["markets"]))

    def test_nested_market_event_identity_mismatch_fails_closed(self):
        class Bad(EventDiscoveryClient):
            def live_public_events(self,**kwargs):
                page=super().live_public_events(**kwargs)
                page["events"][0]["markets"][0]["event_ticker"]="WRONG-EVENT"
                return page

        with self.assertRaises(ValueError):
            build_prospective_kalshi_plan(
                client=Bad(),
                planned_at=NOW,
                market_count=22,
            )


if __name__=="__main__":
    unittest.main()

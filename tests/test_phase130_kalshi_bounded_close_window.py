import unittest
from datetime import datetime, timedelta, timezone

from signal_vault.kalshi_prospective_collector import (
    PLAN_POLICY,
    build_prospective_kalshi_plan,
)

UTC=timezone.utc
NOW=datetime(2026,10,1,18,0,tzinfo=UTC)


def iso(value):
    return value.astimezone(UTC).isoformat().replace("+00:00","Z")


class WindowFirstClient:
    supports_event_discovery=True

    def __init__(self):
        self.window_calls=[]
        self.event_calls=[]

    def live_public_markets_close_window(
        self,*,min_close_ts,max_close_ts,limit=1000,cursor=None
    ):
        self.window_calls.append({
            "min_close_ts":min_close_ts,
            "max_close_ts":max_close_ts,
            "limit":limit,
            "cursor":cursor,
        })
        markets=[]
        for event_index in range(11):
            for leg in range(2):
                markets.append({
                    "ticker":f"BW-{event_index:02d}-{leg}",
                    "event_ticker":f"EVENT-{event_index:02d}",
                    "market_type":"binary",
                    "status":"active",
                    "close_time":iso(
                        NOW+timedelta(hours=30+event_index*2+leg)
                    ),
                    "mve_collection_ticker":None,
                    "is_provisional":False,
                    "can_close_early":False,
                })
        return {"markets":markets,"cursor":"unused-next-page"}

    def live_public_events(self,**kwargs):
        self.event_calls.append(kwargs)
        raise AssertionError("bounded market discovery must be preferred")

    def live_public_market(self,ticker):
        raise AssertionError(ticker)


class KalshiBoundedCloseWindowDiscoveryTests(unittest.TestCase):
    def test_bounded_market_window_is_preferred_over_event_fallback(self):
        client=WindowFirstClient()
        plan=build_prospective_kalshi_plan(
            client=client,
            planned_at=NOW,
            market_count=22,
        )
        self.assertEqual(plan["policy_version"],PLAN_POLICY)
        self.assertEqual(
            plan["discovery_source"],
            "PUBLIC_MARKETS_BOUNDED_CLOSE_WINDOW",
        )
        self.assertEqual(plan["planned_market_count"],22)
        self.assertGreaterEqual(
            len({m["event_ticker"] for m in plan["markets"]}),
            10,
        )
        self.assertEqual(len(client.window_calls),1)
        self.assertEqual(client.event_calls,[])
        call=client.window_calls[0]
        self.assertGreater(call["max_close_ts"],call["min_close_ts"])
        self.assertEqual(call["limit"],1000)
        self.assertTrue(plan["sample_target_reached_before_catalog_exhaustion"])
        self.assertFalse(plan["selection_uses_price"])
        self.assertFalse(plan["selection_uses_outcome_direction"])
        self.assertFalse(plan["selection_uses_historical_pnl"])
        self.assertEqual(plan["network_methods"],["GET"])
        self.assertEqual(plan["credentials_accessed"],"NONE")
        self.assertEqual(plan["demo_order_submission"],"DISABLED")
        self.assertEqual(plan["live_order_submission"],"DISABLED")


if __name__=="__main__":
    unittest.main()

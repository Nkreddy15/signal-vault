import json
import unittest
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from signal_vault.kalshi_prospective_collector import build_prospective_kalshi_plan
from signal_vault.kalshi_public_research import KalshiPublicResearchClient


UTC=timezone.utc
NOW=datetime(2026,10,1,6,30,tzinfo=UTC)


def iso(value):
    return value.astimezone(UTC).isoformat().replace("+00:00","Z")


class KalshiCloseWindowDiscoveryTests(unittest.TestCase):
    def test_public_client_uses_close_filters_without_status(self):
        seen=[]
        def transport(request,timeout):
            seen.append((request.full_url,timeout))
            return b'{"markets":[],"cursor":""}'

        client=KalshiPublicResearchClient(transport=transport)
        client.live_public_markets_close_window(
            min_close_ts=100,
            max_close_ts=200,
            limit=1000,
            cursor=None,
        )
        self.assertEqual(len(seen),1)
        parsed=urlparse(seen[0][0])
        query=parse_qs(parsed.query)
        self.assertEqual(parsed.path,"/trade-api/v2/markets")
        self.assertEqual(query["limit"],["1000"])
        self.assertEqual(query["min_close_ts"],["100"])
        self.assertEqual(query["max_close_ts"],["200"])
        self.assertEqual(query["mve_filter"],["exclude"])
        self.assertNotIn("status",query)

    def test_prospective_plan_prefers_server_side_close_window(self):
        class WindowClient:
            def __init__(self):
                self.calls=[]
                self.markets=[]
                for event_index in range(11):
                    for leg in range(2):
                        close=NOW+timedelta(hours=30+event_index*2+leg)
                        self.markets.append({
                            "ticker":f"WIN-{event_index:02d}-{leg}",
                            "event_ticker":f"WINEVT-{event_index:02d}",
                            "market_type":"binary",
                            "status":"active",
                            "close_time":iso(close),
                            "mve_collection_ticker":None,
                            "is_provisional":False,
                            "can_close_early":False,
                        })

            def live_public_markets_close_window(
                self,*,min_close_ts,max_close_ts,limit=1000,cursor=None,
            ):
                self.calls.append({
                    "min_close_ts":min_close_ts,
                    "max_close_ts":max_close_ts,
                    "limit":limit,
                    "cursor":cursor,
                })
                return {"markets":[dict(x) for x in self.markets],"cursor":""}

            def live_public_markets(self,**kwargs):
                raise AssertionError("unbounded open-market discovery must not be used")

            def live_public_market(self,ticker):
                raise AssertionError("planning does not need per-market quote GETs")

        client=WindowClient()
        plan=build_prospective_kalshi_plan(
            client=client,
            planned_at=NOW,
            market_count=22,
        )
        self.assertEqual(plan["planned_market_count"],22)
        self.assertEqual(plan["discovery_pages"],1)
        self.assertEqual(len(client.calls),1)
        call=client.calls[0]
        self.assertEqual(call["limit"],1000)
        self.assertLess(
            call["min_close_ts"],
            int((NOW+timedelta(hours=25)).timestamp()),
        )
        self.assertGreater(
            call["max_close_ts"],
            int((NOW+timedelta(days=30)).timestamp()),
        )

    def test_close_window_still_relies_on_local_status_validation(self):
        class ClosedOnlyClient:
            def live_public_markets_close_window(self,**kwargs):
                markets=[]
                for event_index in range(11):
                    for leg in range(2):
                        markets.append({
                            "ticker":f"CLOSED-{event_index:02d}-{leg}",
                            "event_ticker":f"CLOSEDEVT-{event_index:02d}",
                            "market_type":"binary",
                            "status":"closed",
                            "close_time":iso(NOW+timedelta(days=2)),
                            "mve_collection_ticker":None,
                            "is_provisional":False,
                        })
                return {"markets":markets,"cursor":""}

            def live_public_markets(self,**kwargs):
                raise AssertionError("fallback should not be used")

            def live_public_market(self,ticker):
                raise AssertionError

        with self.assertRaises(ValueError):
            build_prospective_kalshi_plan(
                client=ClosedOnlyClient(),
                planned_at=NOW,
                market_count=22,
            )


if __name__=="__main__":
    unittest.main()

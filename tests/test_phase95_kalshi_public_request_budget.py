import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from signal_vault.kalshi_cloud_sidecar import (
    ACTIVATION_ENV,
    ACTIVATION_VALUE,
    MAX_PUBLIC_GETS_PER_TICK,
    ROOT_ENV,
    _BudgetedPublicClient,
    run_kalshi_sidecar_once,
)


UTC=timezone.utc
NOW=datetime(2026,10,1,12,0,tzinfo=UTC)


def iso(value):
    return value.astimezone(UTC).isoformat().replace("+00:00","Z")


class InnerClient:
    def __init__(self):
        self.calls=[]

    def live_public_markets(self, **kwargs):
        self.calls.append(("markets",kwargs))
        return {"markets":[],"cursor":""}

    def live_public_market(self,ticker):
        self.calls.append(("market",ticker))
        return {"market":{"ticker":ticker}}


class PlanningClient:
    def __init__(self):
        markets=[]
        for event_index in range(11):
            for leg in range(2):
                close=NOW+timedelta(hours=30+event_index*3+leg)
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

    def live_public_market(self,ticker):
        return {
            "market":next(dict(x) for x in self.markets if x["ticker"]==ticker)
        }


class KalshiPublicRequestBudgetTests(unittest.TestCase):
    def test_budget_wrapper_rejects_request_after_exact_cap(self):
        inner=InnerClient()
        client=_BudgetedPublicClient(inner,maximum=2)
        client.live_public_markets(status="open",limit=1,cursor=None)
        client.live_public_market("TEST")
        self.assertEqual(client.request_count,2)
        with self.assertRaises(RuntimeError):
            client.live_public_market("TEST2")
        self.assertEqual(client.request_count,2)
        self.assertEqual(len(inner.calls),2)

    def test_first_plan_reports_exact_public_request_usage_and_budget(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)/"forward"
        root.mkdir(mode=0o700)
        root.chmod(0o700)
        result=run_kalshi_sidecar_once(
            env={
                ROOT_ENV:str(root),
                ACTIVATION_ENV:ACTIVATION_VALUE,
            },
            now=NOW,
            client_factory=PlanningClient,
        )
        self.assertEqual(
            result["status"],
            "PRECOMMITTED_KALSHI_MARKET_PLAN",
        )
        self.assertEqual(result["network_requests"],1)
        self.assertEqual(result["public_get_requests_used"],1)
        self.assertEqual(
            result["public_get_budget"],
            MAX_PUBLIC_GETS_PER_TICK,
        )
        self.assertLessEqual(
            result["public_get_requests_used"],
            result["public_get_budget"],
        )
        self.assertEqual(result["credentials_accessed"],"NONE")
        self.assertEqual(result["demo_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")

    def test_budget_constant_is_bounded_for_hourly_cloud_collection(self):
        self.assertEqual(MAX_PUBLIC_GETS_PER_TICK,25)
        self.assertGreaterEqual(MAX_PUBLIC_GETS_PER_TICK,20)
        self.assertLessEqual(MAX_PUBLIC_GETS_PER_TICK,50)


if __name__=="__main__":
    unittest.main()

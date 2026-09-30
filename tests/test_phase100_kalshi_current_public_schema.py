import unittest
from datetime import datetime, timedelta, timezone

from signal_vault.kalshi_prospective_collector import (
    build_prospective_kalshi_plan,
)


UTC=timezone.utc
NOW=datetime(2026,9,30,23,8,tzinfo=UTC)


def iso(value):
    return value.astimezone(UTC).isoformat().replace("+00:00","Z")


class CurrentSchemaClient:
    def __init__(self):
        self.markets=[]
        for event_index in range(11):
            for leg in range(2):
                close=NOW+timedelta(hours=30+event_index*2+leg)
                self.markets.append({
                    "ticker":f"MKT-{event_index:02d}-{leg}",
                    "event_ticker":f"EVT-{event_index:02d}",
                    # Intentionally NO market_type field: current public
                    # Market schema still represents YES/NO markets.
                    "status":"open",
                    "close_time":iso(close),
                    "mve_collection_ticker":None,
                    "is_provisional":False,
                    "can_close_early":False,
                    "yes_bid_dollars":"0.40",
                    "yes_ask_dollars":"0.42",
                    "last_price_dollars":"0.41",
                })

    def live_public_markets(self, *, status="open", limit=1000, cursor=None):
        return {"markets":[dict(x) for x in self.markets],"cursor":""}


class KalshiCurrentPublicSchemaTests(unittest.TestCase):
    def test_plan_accepts_current_public_market_objects_without_market_type(self):
        plan=build_prospective_kalshi_plan(
            client=CurrentSchemaClient(),
            planned_at=NOW,
            market_count=22,
        )
        self.assertEqual(plan["planned_market_count"],22)
        self.assertGreaterEqual(
            len({x["event_ticker"] for x in plan["markets"]}),
            10,
        )
        self.assertFalse(plan["selection_uses_price"])
        self.assertFalse(plan["selection_uses_outcome_direction"])
        self.assertEqual(plan["network_methods"],["GET"])
        self.assertEqual(plan["demo_order_submission"],"DISABLED")
        self.assertEqual(plan["live_order_submission"],"DISABLED")

    def test_closed_market_is_still_structurally_ineligible(self):
        client=CurrentSchemaClient()
        for market in client.markets:
            market["status"]="closed"
        with self.assertRaises(ValueError):
            build_prospective_kalshi_plan(
                client=client,
                planned_at=NOW,
                market_count=22,
            )


if __name__=="__main__":
    unittest.main()

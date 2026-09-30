import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from signal_vault.kalshi_prospective_collector import (
    build_prospective_kalshi_plan,
    collect_due_kalshi_snapshots,
)


UTC=timezone.utc
NOW=datetime(2026,9,30,23,45,tzinfo=UTC)


def iso(value):
    return value.astimezone(UTC).isoformat().replace("+00:00","Z")


class CurrentSchemaClient:
    def __init__(self, *, object_status="active", market_type="binary"):
        self.object_status=object_status
        self.market_type=market_type
        self.markets=[]
        for event_index in range(11):
            for leg in range(2):
                close=NOW+timedelta(hours=30+event_index*2+leg)
                self.markets.append({
                    "ticker":f"MKT-{event_index:02d}-{leg}",
                    "event_ticker":f"EVT-{event_index:02d}",
                    "market_type":market_type,
                    "status":object_status,
                    "close_time":iso(close),
                    "mve_collection_ticker":None,
                    "is_provisional":False,
                    "can_close_early":False,
                    "yes_bid_dollars":"0.40",
                    "yes_ask_dollars":"0.42",
                    "last_price_dollars":"0.41",
                })

    def live_public_markets(self, *, status="open", limit=1000, cursor=None):
        self.requested_status=status
        return {"markets":[dict(x) for x in self.markets],"cursor":""}

    def live_public_market(self, ticker):
        market=next(x for x in self.markets if x["ticker"]==ticker)
        return {"market":dict(market)}


class KalshiCurrentPublicSchemaTests(unittest.TestCase):
    def test_status_open_query_accepts_current_active_binary_objects(self):
        client=CurrentSchemaClient(object_status="active",market_type="binary")
        plan=build_prospective_kalshi_plan(
            client=client,
            planned_at=NOW,
            market_count=22,
        )
        self.assertEqual(client.requested_status,"open")
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

    def test_active_binary_single_market_is_valid_at_fixed_horizon(self):
        client=CurrentSchemaClient(object_status="active",market_type="binary")
        plan=build_prospective_kalshi_plan(
            client=client,
            planned_at=NOW,
            market_count=22,
        )
        first=min(
            plan["markets"],
            key=lambda x: datetime.fromisoformat(x["close_time"]),
        )
        due=datetime.fromisoformat(first["close_time"])-timedelta(hours=24)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            root.chmod(0o700)
            result=collect_due_kalshi_snapshots(
                plan=plan,
                now=due+timedelta(minutes=1),
                output_root=root,
                client=client,
            )
        self.assertGreaterEqual(result["captured_count"],1)
        self.assertTrue(result["captured"][0]["decision_valid"])
        self.assertEqual(result["network_methods"],["GET"])
        self.assertEqual(result["demo_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")

    def test_legacy_open_binary_object_remains_compatible(self):
        plan=build_prospective_kalshi_plan(
            client=CurrentSchemaClient(object_status="open",market_type="binary"),
            planned_at=NOW,
            market_count=22,
        )
        self.assertEqual(plan["planned_market_count"],22)

    def test_closed_or_nonbinary_market_is_structurally_ineligible(self):
        for status,market_type in (
            ("closed","binary"),
            ("active","scalar"),
            ("active",None),
        ):
            with self.subTest(status=status,market_type=market_type):
                with self.assertRaises(ValueError):
                    build_prospective_kalshi_plan(
                        client=CurrentSchemaClient(
                            object_status=status,
                            market_type=market_type,
                        ),
                        planned_at=NOW,
                        market_count=22,
                    )


if __name__=="__main__":
    unittest.main()

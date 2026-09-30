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


UTC=timezone.utc
NOW=datetime(2026,10,1,12,0,tzinfo=UTC)


def iso(value):
    return value.astimezone(UTC).isoformat().replace("+00:00","Z")


class QuoteEdgeClient:
    def __init__(self):
        close=NOW+timedelta(hours=30)
        markets=[]
        for event_index in range(10):
            for leg in range(2):
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
        self.markets={x["ticker"]:x for x in markets}

    def live_public_markets(self, *, status="open", limit=1000, cursor=None):
        return {"markets":[dict(x) for x in self.markets.values()],"cursor":""}

    def live_public_market(self,ticker):
        return {"market":dict(self.markets[ticker])}


class KalshiPerMarketQuoteFailClosedTests(unittest.TestCase):
    def make_root(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)/"kalshi"
        root.mkdir(mode=0o700)
        root.chmod(0o700)
        return root

    def test_two_bad_quotes_do_not_block_other_due_markets(self):
        client=QuoteEdgeClient()
        plan=build_prospective_kalshi_plan(
            client=client,
            planned_at=NOW,
        )
        root=self.make_root()
        archive_prospective_kalshi_plan(plan,output_root=root)

        selected=[x["ticker"] for x in plan["markets"]]
        missing=selected[0]
        crossed=selected[1]
        client.markets[missing]["last_price_dollars"]=None
        client.markets[crossed]["yes_bid_dollars"]="0.70"
        client.markets[crossed]["yes_ask_dollars"]="0.30"

        close=datetime.fromisoformat(plan["markets"][0]["close_time"])
        result=collect_due_kalshi_snapshots(
            plan=plan,
            now=close-timedelta(hours=24)+timedelta(minutes=7),
            output_root=root,
            client=client,
        )

        due=[
            x for x in result["captured"]
            if x["horizon_seconds"]==86400
        ]
        self.assertEqual(len(due),20)
        invalid=[x for x in due if x["decision_valid"] is False]
        valid=[x for x in due if x["decision_valid"] is True]
        self.assertEqual({x["ticker"] for x in invalid},{missing,crossed})
        self.assertEqual(len(valid),18)

        for ticker in (missing,crossed):
            receipt=json.loads(
                (root/f"kalshi-forward-{ticker}-86400s.json").read_text()
            )
            self.assertFalse(receipt["decision_valid"])
            self.assertEqual(
                receipt["invalid_reason"],
                "MISSING_INVALID_OR_CROSSED_PUBLIC_QUOTE_AT_FIXED_HORIZON",
            )
            self.assertIsNone(receipt["yes_bid_dollars"])
            self.assertIsNone(receipt["yes_ask_dollars"])
            self.assertIsNone(receipt["last_price_dollars"])
            self.assertFalse(receipt["outcome_direction_recorded"])
            self.assertNotIn("result",receipt)

        self.assertEqual(result["historical_backfill_count"],0)
        self.assertEqual(result["post_settlement_decision_count"],0)
        self.assertEqual(result["demo_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")

    def test_identity_mismatch_remains_hard_failure(self):
        client=QuoteEdgeClient()
        plan=build_prospective_kalshi_plan(client=client,planned_at=NOW)
        root=self.make_root()
        ticker=plan["markets"][0]["ticker"]
        client.markets[ticker]["event_ticker"]="WRONG-EVENT"
        close=datetime.fromisoformat(plan["markets"][0]["close_time"])
        with self.assertRaises(ValueError):
            collect_due_kalshi_snapshots(
                plan=plan,
                now=close-timedelta(hours=24)+timedelta(minutes=7),
                output_root=root,
                client=client,
            )


if __name__=="__main__":
    unittest.main()

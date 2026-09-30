import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from signal_vault.kalshi_prospective_archive_audit import (
    audit_kalshi_prospective_archive,
)
from signal_vault.kalshi_prospective_collector import (
    HORIZONS,
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
        return {"market":dict(self.markets[ticker])}


class KalshiProspectiveArchiveAuditTests(unittest.TestCase):
    def build_complete(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)/"kalshi"
        root.mkdir(mode=0o700)
        root.chmod(0o700)
        client=FakeClient()
        plan=build_prospective_kalshi_plan(client=client,planned_at=NOW)
        archive_prospective_kalshi_plan(plan,output_root=root)

        due=[]
        for market in plan["markets"]:
            close=datetime.fromisoformat(market["close_time"])
            for horizon in HORIZONS:
                due.append((close-timedelta(seconds=horizon),market["ticker"],horizon))
        for target,_,_ in sorted(due):
            collect_due_kalshi_snapshots(
                plan=plan,
                now=target+timedelta(minutes=7),
                output_root=root,
                client=client,
            )

        max_close=max(datetime.fromisoformat(x["close_time"]) for x in plan["markets"])
        for market in plan["markets"]:
            ticker=market["ticker"]
            close=datetime.fromisoformat(market["close_time"])
            client.markets[ticker].update({
                "status":"settled",
                "result":"yes" if ticker.endswith("-0") else "no",
                "settlement_ts":iso(close+timedelta(minutes=10)),
            })
        collect_due_kalshi_settlements(
            plan=plan,
            now=max_close+timedelta(hours=2),
            output_root=root,
            client=client,
        )
        return root,plan

    def test_complete_20_market_archive_has_full_coverage_and_ten_events(self):
        root,plan=self.build_complete()
        result=audit_kalshi_prospective_archive(root)
        self.assertEqual(result["planned_market_count"],20)
        self.assertEqual(result["valid_prospective_market_count"],20)
        self.assertEqual(result["missed_or_invalid_market_count"],0)
        self.assertEqual(result["pending_market_count"],0)
        self.assertEqual(result["distinct_valid_event_count"],10)
        self.assertEqual(result["capture_coverage_fraction"],"1")
        self.assertTrue(result["source_integrity_passed"])
        self.assertFalse(result["outcome_direction_used_for_market_selection"])
        self.assertEqual(result["historical_backfill_count"],0)
        self.assertEqual(result["post_settlement_decision_count"],0)
        self.assertEqual(result["network_requests"],"NONE")
        self.assertEqual(result["demo_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")
        self.assertEqual(result["plan_sha256"],plan["plan_sha256"])

    def test_missing_decision_snapshot_becomes_missed_invalid_not_backfilled(self):
        root,plan=self.build_complete()
        ticker=plan["markets"][0]["ticker"]
        (root/f"kalshi-forward-{ticker}-86400s.json").unlink()
        result=audit_kalshi_prospective_archive(root)
        self.assertEqual(result["valid_prospective_market_count"],19)
        self.assertEqual(result["missed_or_invalid_market_count"],1)
        self.assertEqual(result["pending_market_count"],0)
        self.assertEqual(result["capture_coverage_fraction"],"0.95")
        market=next(x for x in result["markets"] if x["ticker"]==ticker)
        self.assertEqual(market["status"],"MISSED_OR_INVALID")
        self.assertTrue(any("MISSING_" in x for x in market["invalid_reasons"]))
        self.assertEqual(result["historical_backfill_count"],0)

    def test_missing_settlement_is_pending_until_public_result_arrives(self):
        root,plan=self.build_complete()
        ticker=plan["markets"][0]["ticker"]
        (root/f"kalshi-settlement-{ticker}.json").unlink()
        result=audit_kalshi_prospective_archive(root)
        self.assertEqual(result["valid_prospective_market_count"],19)
        self.assertEqual(result["missed_or_invalid_market_count"],0)
        self.assertEqual(result["pending_market_count"],1)

    def test_snapshot_cannot_be_edited_to_include_outcome(self):
        root,plan=self.build_complete()
        ticker=plan["markets"][0]["ticker"]
        path=root/f"kalshi-forward-{ticker}-86400s.json"
        body=json.loads(path.read_text())
        body["result"]="yes"
        path.write_text(
            json.dumps(body,sort_keys=True,separators=(",",":"))+"\n"
        )
        path.chmod(0o600)
        with self.assertRaises(ValueError):
            audit_kalshi_prospective_archive(root)

    def test_unexpected_file_or_noncanonical_json_fails_closed(self):
        root,_=self.build_complete()
        extra=root/"notes.txt"
        extra.write_text("not evidence")
        extra.chmod(0o600)
        with self.assertRaises(ValueError):
            audit_kalshi_prospective_archive(root)


if __name__=="__main__":
    unittest.main()

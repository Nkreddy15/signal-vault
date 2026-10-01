import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from signal_vault.all_market_forward_status import (
    _equity_status,
    _kalshi_status,
    all_market_forward_status,
)
from signal_vault.equity_cloud_sidecar import CHILD as EQUITY_CHILD
from signal_vault.kalshi_cloud_sidecar import CHILD as KALSHI_CHILD
from signal_vault.kalshi_prospective_collector import (
    archive_prospective_kalshi_plan,
    build_prospective_kalshi_plan,
)


UTC=timezone.utc
NOW=datetime(2026,10,1,12,0,tzinfo=UTC)


def iso(value):
    return value.astimezone(UTC).isoformat().replace("+00:00","Z")


class FakeKalshiClient:
    def __init__(self):
        self.markets=[]
        for event_index in range(10):
            for leg in range(2):
                close=NOW+timedelta(hours=30+event_index*3+leg)
                self.markets.append({
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

    def live_public_markets(self, *, status="open", limit=1000, cursor=None):
        return {"markets":[dict(x) for x in self.markets],"cursor":""}


class AllMarketForwardStatusTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)/"forward"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)

    def test_missing_stock_and_kalshi_children_are_reported_without_creation(self):
        equity=_equity_status(self.root)
        kalshi=_kalshi_status(self.root)
        self.assertEqual(equity["status"],"NOT_STARTED")
        self.assertEqual(kalshi["status"],"NOT_STARTED")
        self.assertFalse((self.root/EQUITY_CHILD).exists())
        self.assertFalse((self.root/KALSHI_CHILD).exists())

    def test_stock_raw_counts_are_not_claimed_as_gate_pass(self):
        child=self.root/EQUITY_CHILD
        child.mkdir(mode=0o700)
        child.chmod(0o700)
        for day in range(10):
            plan=child/f"equity-forward-plan-202610{day+1:02d}-{'a'*16}.json"
            plan.write_text("{}")
            plan.chmod(0o600)
        for hour in range(60):
            receipt=child/f"equity-forward-20261001T{hour%24:02d}00Z-{hour:016x}.json"
            receipt.write_text("{}")
            receipt.chmod(0o600)
        # Malformed raw artifacts must fail closed rather than be counted as
        # readiness evidence merely because enough filenames exist.
        with self.assertRaises(ValueError):
            _equity_status(self.root)

    def test_kalshi_plan_and_artifact_progress_are_reported_conservatively(self):
        child=self.root/KALSHI_CHILD
        child.mkdir(mode=0o700)
        child.chmod(0o700)
        client=FakeKalshiClient()
        plan=build_prospective_kalshi_plan(client=client,planned_at=NOW)
        archive_prospective_kalshi_plan(plan,output_root=child)
        for index in range(7):
            p=child/f"kalshi-forward-MKT-00-0-{86400 if index%2==0 else 21600}s-{index}.json"
            p.write_text("{}")
            p.chmod(0o600)
        for index in range(3):
            p=child/f"kalshi-settlement-MKT-{index:02d}.json"
            p.write_text("{}")
            p.chmod(0o600)
        result=_kalshi_status(self.root)
        self.assertTrue(result["plan_present"])
        self.assertEqual(result["planned_market_count"],20)
        self.assertGreaterEqual(result["planned_distinct_event_count"],10)
        self.assertEqual(result["prospective_decision_snapshots"],7)
        self.assertEqual(result["settlement_receipts"],3)
        self.assertEqual(result["raw_decision_snapshots_remaining"],33)
        self.assertEqual(result["raw_settlement_receipts_remaining"],17)
        self.assertTrue(result["artifact_counts_are_not_gate_pass"])
        self.assertTrue(result["offline_integrity_audit_required"])
        self.assertEqual(result["demo_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")

    def test_tampered_kalshi_plan_fails_closed_instead_of_reporting_progress(self):
        child=self.root/KALSHI_CHILD
        child.mkdir(mode=0o700)
        child.chmod(0o700)
        plan=build_prospective_kalshi_plan(
            client=FakeKalshiClient(),planned_at=NOW
        )
        path=archive_prospective_kalshi_plan(plan,output_root=child)
        body=json.loads(path.read_text())
        body["selection_uses_price"]=True
        path.write_text(
            json.dumps(body,sort_keys=True,separators=(",",":"))+"\n"
        )
        path.chmod(0o600)
        with self.assertRaises(ValueError):
            _kalshi_status(self.root)

    def test_top_level_status_is_network_and_credential_free(self):
        fake_crypto={
            "kind":"RAILWAY_BTC_FIRST_SIX_CRYPTO_OFFLINE_STATUS",
            "status":"READ_ONLY_STATUS_AVAILABLE",
            "network_requests":"NONE",
            "credential_access":"NONE",
            "broker_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        }
        with patch(
            "signal_vault.all_market_forward_status.combined_offline_status",
            return_value=fake_crypto,
        ) as mocked:
            result=all_market_forward_status(environ={},root=self.root)
        mocked.assert_called_once()
        self.assertEqual(result["network_requests"],"NONE")
        self.assertEqual(result["credential_access"],"NONE")
        self.assertEqual(result["broker_order_submission"],"DISABLED")
        self.assertEqual(result["paper_order_submission"],"DISABLED")
        self.assertEqual(result["demo_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")
        self.assertFalse((self.root/EQUITY_CHILD).exists())
        self.assertFalse((self.root/KALSHI_CHILD).exists())


if __name__=="__main__":
    unittest.main()

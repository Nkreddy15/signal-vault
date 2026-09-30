import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from signal_vault.all_market_forward_status import (
    _equity_status,
    _kalshi_status,
)
from signal_vault.equity_cloud_sidecar import CHILD as EQUITY_CHILD
from signal_vault.kalshi_cloud_sidecar import CHILD as KALSHI_CHILD


UTC=timezone.utc
NOW=datetime(2026,11,1,12,0,tzinfo=UTC)


def private_file(path:Path, text="{}"):
    path.write_text(text)
    path.chmod(0o600)


class AutoSourceIntegrityAuditTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)/"forward"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)

    def test_equity_threshold_triggers_offline_integrity_audit(self):
        child=self.root/EQUITY_CHILD
        child.mkdir(mode=0o700)
        child.chmod(0o700)
        for i in range(10):
            private_file(
                child/f"equity-forward-plan-202610{i+1:02d}-{'a'*16}.json"
            )
        for i in range(60):
            private_file(
                child/f"equity-forward-20261001T{i%24:02d}{i%60:02d}Z-{i:016x}.json"
            )
        fake_plan={"expected_core_opens_utc":[]}
        audit={
            "current_segment_prospective_core_hours_per_asset":60,
            "current_segment_distinct_xnys_sessions":10,
            "source_integrity_passed":True,
            "network_requests":"NONE",
            "paper_order_submission":"DISABLED",
            "live_order_submission":"DISABLED",
        }
        with patch(
            "signal_vault.all_market_forward_status._read_json",
            return_value=fake_plan,
        ), patch(
            "signal_vault.all_market_forward_status._validate_equity_plan",
            return_value=(None,(), "a"*64),
        ), patch(
            "signal_vault.all_market_forward_status.audit_equity_forward_archive",
            return_value=audit,
        ) as audited:
            result=_equity_status(self.root,as_of=NOW)
        audited.assert_called_once_with(child)
        self.assertEqual(result["offline_integrity_audit_status"],"AVAILABLE")
        self.assertEqual(
            result["current_segment_integrity_verified_core_hours"],60
        )
        self.assertEqual(
            result["current_segment_integrity_verified_sessions"],10
        )
        self.assertTrue(
            result["prospective_source_integrity_ready_for_shadow_scoring"]
        )
        self.assertTrue(result["artifact_counts_are_not_gate_pass"])
        self.assertEqual(result["paper_order_submission"],"DISABLED")

    def test_equity_below_threshold_does_not_run_integrity_audit(self):
        child=self.root/EQUITY_CHILD
        child.mkdir(mode=0o700)
        child.chmod(0o700)
        private_file(child/f"equity-forward-plan-20261001-{'a'*16}.json")
        fake_plan={"expected_core_opens_utc":[]}
        with patch(
            "signal_vault.all_market_forward_status._read_json",
            return_value=fake_plan,
        ), patch(
            "signal_vault.all_market_forward_status._validate_equity_plan",
            return_value=(None,(), "a"*64),
        ), patch(
            "signal_vault.all_market_forward_status.audit_equity_forward_archive",
            side_effect=AssertionError("audit must not run early"),
        ) as audited:
            result=_equity_status(self.root,as_of=NOW)
        audited.assert_not_called()
        self.assertEqual(
            result["offline_integrity_audit_status"],
            "NOT_READY_RAW_EVIDENCE_INCOMPLETE",
        )
        self.assertFalse(
            result["prospective_source_integrity_ready_for_shadow_scoring"]
        )

    def test_kalshi_threshold_triggers_offline_integrity_audit(self):
        child=self.root/KALSHI_CHILD
        child.mkdir(mode=0o700)
        child.chmod(0o700)
        private_file(child/f"kalshi-prospective-plan-{'a'*16}.json")
        for i in range(40):
            private_file(child/f"kalshi-forward-TEST-{i:02d}-21600s.json")
        for i in range(20):
            private_file(child/f"kalshi-settlement-TEST-{i:02d}.json")
        plan={"plan_sha256":"a"*64}
        markets=[
            {
                "ticker":f"TEST-{i:02d}",
                "event_ticker":f"EVENT-{i//2:02d}",
                "close_time":"2026-10-01T12:00:00+00:00",
            }
            for i in range(20)
        ]
        audit={
            "valid_prospective_market_count":20,
            "distinct_valid_event_count":10,
            "source_integrity_passed":True,
            "network_requests":"NONE",
            "demo_order_submission":"DISABLED",
            "live_order_submission":"DISABLED",
        }
        with patch(
            "signal_vault.all_market_forward_status._read_json",
            return_value=plan,
        ), patch(
            "signal_vault.all_market_forward_status.validate_prospective_kalshi_plan",
            return_value=tuple(markets),
        ), patch(
            "signal_vault.all_market_forward_status.audit_kalshi_prospective_archive",
            return_value=audit,
        ) as audited:
            result=_kalshi_status(self.root,as_of=NOW)
        audited.assert_called_once_with(child)
        self.assertEqual(result["offline_integrity_audit_status"],"AVAILABLE")
        self.assertEqual(result["integrity_verified_valid_markets"],20)
        self.assertEqual(result["integrity_verified_distinct_events"],10)
        self.assertTrue(
            result["prospective_source_integrity_ready_for_shadow_scoring"]
        )
        self.assertTrue(result["artifact_counts_are_not_gate_pass"])
        self.assertEqual(result["demo_order_submission"],"DISABLED")

    def test_integrity_audit_failure_is_visible_and_never_claims_ready(self):
        child=self.root/KALSHI_CHILD
        child.mkdir(mode=0o700)
        child.chmod(0o700)
        private_file(child/f"kalshi-prospective-plan-{'a'*16}.json")
        for i in range(40):
            private_file(child/f"kalshi-forward-TEST-{i:02d}-21600s.json")
        for i in range(20):
            private_file(child/f"kalshi-settlement-TEST-{i:02d}.json")
        markets=[
            {
                "ticker":f"TEST-{i:02d}",
                "event_ticker":f"EVENT-{i//2:02d}",
                "close_time":"2026-10-01T12:00:00+00:00",
            }
            for i in range(20)
        ]
        with patch(
            "signal_vault.all_market_forward_status._read_json",
            return_value={"plan_sha256":"a"*64},
        ), patch(
            "signal_vault.all_market_forward_status.validate_prospective_kalshi_plan",
            return_value=tuple(markets),
        ), patch(
            "signal_vault.all_market_forward_status.audit_kalshi_prospective_archive",
            side_effect=ValueError("fixture integrity failure"),
        ):
            result=_kalshi_status(self.root,as_of=NOW)
        self.assertEqual(result["offline_integrity_audit_status"],"FAILED")
        self.assertEqual(
            result["offline_integrity_audit"]["failure_class"],
            "ValueError",
        )
        self.assertFalse(
            result["prospective_source_integrity_ready_for_shadow_scoring"]
        )
        self.assertEqual(result["live_order_submission"],"DISABLED")


if __name__=="__main__":
    unittest.main()

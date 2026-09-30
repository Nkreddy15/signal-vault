import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from signal_vault.kalshi_cloud_sidecar import CHILD as KALSHI_CHILD
from signal_vault.railway_all_markets_research_cron import (
    combined_all_markets_once,
)
from signal_vault.railway_btc_first_dual_cron import (
    BTC_FINGERPRINT_EXCLUDED_CHILDREN,
)


UTC=timezone.utc


class RailwayAllMarketsCronTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)/"forward"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        self.btc=self.root/"observations.sqlite3"
        self.btc.write_bytes(b"original-btc-evidence")
        self.btc.chmod(0o600)

    @staticmethod
    def healthy_core(**kwargs):
        return {
            "crypto_btc_status":"SAFE_NO_NEW_OBSERVATION",
            "equity_status":"NO_DUE_CORE_HOUR",
            "btc_evidence_changed_during_equity_stage":False,
            "broker_order_submission":"DISABLED",
            "paper_order_submission":"DISABLED",
            "live_order_submission":"DISABLED",
        }

    def test_three_explicit_research_children_are_fingerprint_exclusions(self):
        self.assertEqual(len(BTC_FINGERPRINT_EXCLUDED_CHILDREN),3)
        self.assertEqual(
            BTC_FINGERPRINT_EXCLUDED_CHILDREN[2],
            KALSHI_CHILD,
        )
        self.assertEqual(len(set(BTC_FINGERPRINT_EXCLUDED_CHILDREN)),3)

    def test_kalshi_child_write_does_not_change_original_btc_fingerprint(self):
        calls=[]
        def kalshi_runner(*,env,now):
            calls.append(now)
            child=self.root/KALSHI_CHILD
            child.mkdir(mode=0o700,exist_ok=True)
            child.chmod(0o700)
            evidence=child/"kalshi-prospective-plan-test.json"
            evidence.write_text("kalshi-public-get-only")
            evidence.chmod(0o600)
            return {
                "status":"PRECOMMITTED_KALSHI_MARKET_PLAN",
                "credentials_accessed":"NONE",
                "demo_order_submission":"DISABLED",
                "live_order_submission":"DISABLED",
            }

        result=combined_all_markets_once(
            now=datetime(2026,9,30,22,7,tzinfo=UTC),
            environ={},
            btc_root=self.root,
            core_runner=self.healthy_core,
            kalshi_runner=kalshi_runner,
        )
        self.assertEqual(
            result["kalshi_status"],
            "PRECOMMITTED_KALSHI_MARKET_PLAN",
        )
        self.assertFalse(
            result["btc_evidence_changed_during_kalshi_stage"]
        )
        self.assertTrue(result["original_BTC_status_preserved"])
        self.assertFalse(result["new_Railway_service_created"])
        self.assertFalse(result["new_Railway_volume_created"])
        self.assertFalse(result["new_paid_resource_created"])
        self.assertEqual(result["broker_order_submission"],"DISABLED")
        self.assertEqual(result["paper_order_submission"],"DISABLED")
        self.assertEqual(result["demo_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")
        self.assertEqual(len(calls),1)

    def test_any_original_btc_mutation_during_kalshi_stage_fails_guard(self):
        def bad_kalshi(*,env,now):
            self.btc.write_bytes(b"mutated-original-btc")
            self.btc.chmod(0o600)
            return {"status":"COLLECTION_TICK_COMPLETE"}

        result=combined_all_markets_once(
            now=datetime(2026,9,30,22,7,tzinfo=UTC),
            environ={},
            btc_root=self.root,
            core_runner=self.healthy_core,
            kalshi_runner=bad_kalshi,
        )
        self.assertEqual(
            result["kalshi_status"],
            "FAILED_BTC_EVIDENCE_MUTATION_GUARD",
        )
        self.assertTrue(
            result["btc_evidence_changed_during_kalshi_stage"]
        )
        self.assertFalse(result["original_BTC_status_preserved"])
        self.assertIsNone(
            result["existing_BTC_evidence_deleted_or_reset"]
        )

    def test_kalshi_exception_isolated_when_btc_fingerprint_is_unchanged(self):
        def failing_kalshi(*, env, now):
            raise RuntimeError("fixture failure")

        result=combined_all_markets_once(
            now=datetime(2026,9,30,22,7,tzinfo=UTC),
            environ={},
            btc_root=self.root,
            core_runner=self.healthy_core,
            kalshi_runner=failing_kalshi,
        )
        self.assertEqual(
            result["kalshi_status"],
            "FAILED_SAFE_OR_BLOCKED_KALSHI_SIDECAR_ONLY",
        )
        self.assertEqual(result["kalshi_failure_class"],"RuntimeError")
        self.assertFalse(
            result["btc_evidence_changed_during_kalshi_stage"]
        )
        self.assertTrue(result["original_BTC_status_preserved"])
        self.assertFalse(result["existing_BTC_evidence_deleted_or_reset"])

    def test_kalshi_mutation_then_exception_promotes_to_btc_mutation_guard(self):
        def failing_mutating_kalshi(*, env, now):
            self.btc.write_bytes(b"changed-before-kalshi-exception")
            self.btc.chmod(0o600)
            raise RuntimeError("fixture failure after mutation")

        result=combined_all_markets_once(
            now=datetime(2026,9,30,22,7,tzinfo=UTC),
            environ={},
            btc_root=self.root,
            core_runner=self.healthy_core,
            kalshi_runner=failing_mutating_kalshi,
        )
        self.assertEqual(
            result["kalshi_status"],
            "FAILED_BTC_EVIDENCE_MUTATION_GUARD",
        )
        self.assertEqual(
            result["kalshi_failure_class"],
            "BtcEvidenceFingerprintMismatch",
        )
        self.assertTrue(
            result["btc_evidence_changed_during_kalshi_stage"]
        )
        self.assertFalse(result["original_BTC_status_preserved"])

    def test_unknown_stock_integrity_skips_kalshi_completely(self):
        called=[]
        def unknown_stock_core(**kwargs):
            return {
                "crypto_btc_status":"SAFE_NO_NEW_OBSERVATION",
                "equity_status":"FAILED_SAFE_OR_BLOCKED_EQUITY_SIDECAR_ONLY",
                "btc_evidence_changed_during_equity_stage":None,
                "btc_evidence_integrity_recheck_failure_class":"PermissionError",
            }
        def kalshi(**kwargs):
            called.append(True)
            return {"status":"SHOULD_NOT_RUN"}

        result=combined_all_markets_once(
            now=datetime(2026,9,30,22,7,tzinfo=UTC),
            environ={},
            btc_root=self.root,
            core_runner=unknown_stock_core,
            kalshi_runner=kalshi,
        )
        self.assertEqual(
            result["kalshi_status"],
            "SKIPPED_BTC_INTEGRITY_NOT_PROVEN",
        )
        self.assertEqual(called,[])

    def test_unhealthy_btc_skips_kalshi_completely(self):
        called=[]
        def bad_core(**kwargs):
            return {
                "crypto_btc_status":"BLOCKED_ORIGINAL_BTC_CRON_EXCEPTION",
                "equity_status":"SKIPPED_BTC_NOT_HEALTHY",
            }
        def kalshi(**kwargs):
            called.append(True)
            return {"status":"SHOULD_NOT_RUN"}

        result=combined_all_markets_once(
            now=datetime(2026,9,30,22,7,tzinfo=UTC),
            environ={},
            btc_root=self.root,
            core_runner=bad_core,
            kalshi_runner=kalshi,
        )
        self.assertEqual(
            result["kalshi_status"],
            "SKIPPED_BTC_NOT_HEALTHY",
        )
        self.assertEqual(called,[])

    def test_stock_integrity_failure_skips_kalshi_completely(self):
        called=[]
        def bad_stock_core(**kwargs):
            return {
                "crypto_btc_status":"SAFE_NO_NEW_OBSERVATION",
                "equity_status":"FAILED_BTC_EVIDENCE_MUTATION_GUARD",
                "btc_evidence_changed_during_equity_stage":True,
            }
        def kalshi(**kwargs):
            called.append(True)
            return {"status":"SHOULD_NOT_RUN"}

        result=combined_all_markets_once(
            now=datetime(2026,9,30,22,7,tzinfo=UTC),
            environ={},
            btc_root=self.root,
            core_runner=bad_stock_core,
            kalshi_runner=kalshi,
        )
        self.assertEqual(
            result["kalshi_status"],
            "SKIPPED_BTC_INTEGRITY_NOT_PROVEN",
        )
        self.assertEqual(called,[])

    def test_kalshi_storage_namespace_cannot_be_symlink(self):
        target=self.root/"outside"
        target.mkdir(mode=0o700)
        (self.root/KALSHI_CHILD).symlink_to(target,target_is_directory=True)
        with self.assertRaises(ValueError):
            combined_all_markets_once(
                now=datetime(2026,9,30,22,7,tzinfo=UTC),
                environ={},
                btc_root=self.root,
                core_runner=self.healthy_core,
                kalshi_runner=lambda **kwargs:{"status":"SHOULD_NOT_RUN"},
            )


if __name__=="__main__":
    unittest.main()

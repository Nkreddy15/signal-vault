import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from signal_vault.btc_evidence_fingerprint import (
    fingerprint_btc_evidence_tree,
)
from signal_vault.equity_cloud_sidecar import ROOT_ENV
from signal_vault.railway_btc_first_dual_cron import (
    BASENAME,
    BTC_FINGERPRINT_EXCLUDED_CHILDREN,
)
from signal_vault.railway_multimarket_research_cron import (
    combined_multimarket_once,
)


UTC = timezone.utc


class RailwayMultiMarketCronTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "forward"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        self.btc = self.root / "observations.sqlite3"
        self.btc.write_bytes(b"original-btc-evidence")
        self.btc.chmod(0o600)
        self.calls = []

    @staticmethod
    def healthy_crypto(**kwargs):
        return {
            "btc_status": "SAFE_NO_NEW_OBSERVATION",
            "sidecar_status": "SAFE_NO_NEW_OBSERVATION",
            "btc_evidence_changed_during_sidecar_stage": False,
            "broker_order_submission": "DISABLED",
            "live_trading": "UNAVAILABLE",
        }

    def test_multi_child_fingerprint_is_backward_compatible_and_scoped(self):
        crypto = self.root / BASENAME
        stock = self.root / BTC_FINGERPRINT_EXCLUDED_CHILDREN[1]
        crypto.mkdir(mode=0o700)
        stock.mkdir(mode=0o700)
        (crypto / "c.json").write_text("one")
        (crypto / "c.json").chmod(0o600)
        (stock / "s.json").write_text("one")
        (stock / "s.json").chmod(0o600)

        old = fingerprint_btc_evidence_tree(
            self.root,
            excluded_sidecar_name=BASENAME,
        )
        self.assertEqual(old["excluded_sidecar_child"], BASENAME)
        self.assertEqual(old["excluded_sidecar_children"], [BASENAME])

        both_before = fingerprint_btc_evidence_tree(
            self.root,
            excluded_sidecar_names=BTC_FINGERPRINT_EXCLUDED_CHILDREN,
        )
        (crypto / "c.json").write_text("changed")
        (stock / "s.json").write_text("changed")
        both_after = fingerprint_btc_evidence_tree(
            self.root,
            excluded_sidecar_names=BTC_FINGERPRINT_EXCLUDED_CHILDREN,
        )
        self.assertEqual(
            both_before["tree_sha256"],
            both_after["tree_sha256"],
        )

        self.btc.write_bytes(b"btc-mutated")
        btc_changed = fingerprint_btc_evidence_tree(
            self.root,
            excluded_sidecar_names=BTC_FINGERPRINT_EXCLUDED_CHILDREN,
        )
        self.assertNotEqual(
            both_after["tree_sha256"],
            btc_changed["tree_sha256"],
        )

    def test_stock_child_write_preserves_original_btc_fingerprint(self):
        def equity_runner(*, env, now):
            self.calls.append(("equity", now))
            root = Path(env[ROOT_ENV])
            child = root / BTC_FINGERPRINT_EXCLUDED_CHILDREN[1]
            child.mkdir(mode=0o700, exist_ok=True)
            child.chmod(0o700)
            receipt = child / "equity-forward-test.json"
            receipt.write_text("stock-only")
            receipt.chmod(0o600)
            return {
                "status": "ONE_SIX_STOCK_CORE_HOUR_CAPTURED",
                "broker_order_submission": "DISABLED",
                "live_order_submission": "DISABLED",
            }

        result = combined_multimarket_once(
            now=datetime(2026, 9, 30, 15, 7, tzinfo=UTC),
            environ={ROOT_ENV: str(self.root)},
            btc_root=self.root,
            btc_crypto_runner=self.healthy_crypto,
            equity_runner=equity_runner,
        )
        self.assertEqual(
            result["equity_status"],
            "ONE_SIX_STOCK_CORE_HOUR_CAPTURED",
        )
        self.assertFalse(result["btc_evidence_changed_during_equity_stage"])
        self.assertTrue(result["original_BTC_status_preserved"])
        self.assertFalse(result["new_Railway_service_created"])
        self.assertFalse(result["new_Railway_volume_created"])
        self.assertEqual(result["paper_order_submission"], "DISABLED")
        self.assertEqual(result["live_order_submission"], "DISABLED")
        self.assertEqual(len(self.calls), 1)

    def test_any_original_btc_mutation_during_equity_stage_fails_guard(self):
        def bad_equity_runner(*, env, now):
            self.btc.write_bytes(b"corrupted-by-bad-sidecar")
            self.btc.chmod(0o600)
            return {
                "status": "ONE_SIX_STOCK_CORE_HOUR_CAPTURED",
            }

        result = combined_multimarket_once(
            now=datetime(2026, 9, 30, 15, 7, tzinfo=UTC),
            environ={ROOT_ENV: str(self.root)},
            btc_root=self.root,
            btc_crypto_runner=self.healthy_crypto,
            equity_runner=bad_equity_runner,
        )
        self.assertEqual(
            result["equity_status"],
            "FAILED_BTC_EVIDENCE_MUTATION_GUARD",
        )
        self.assertTrue(result["btc_evidence_changed_during_equity_stage"])
        self.assertFalse(result["original_BTC_status_preserved"])
        self.assertIsNone(result["existing_BTC_evidence_deleted_or_reset"])

    def test_stock_exception_isolated_when_btc_fingerprint_is_unchanged(self):
        def failing_equity_runner(*, env, now):
            raise RuntimeError("fixture failure")

        result = combined_multimarket_once(
            now=datetime(2026, 9, 30, 15, 7, tzinfo=UTC),
            environ={ROOT_ENV: str(self.root)},
            btc_root=self.root,
            btc_crypto_runner=self.healthy_crypto,
            equity_runner=failing_equity_runner,
        )
        self.assertEqual(
            result["equity_status"],
            "FAILED_SAFE_OR_BLOCKED_EQUITY_SIDECAR_ONLY",
        )
        self.assertEqual(result["equity_failure_class"], "RuntimeError")
        self.assertFalse(result["btc_evidence_changed_during_equity_stage"])
        self.assertTrue(result["original_BTC_status_preserved"])
        self.assertFalse(result["existing_BTC_evidence_deleted_or_reset"])
        self.assertEqual(result["crypto_btc_status"], "SAFE_NO_NEW_OBSERVATION")

    def test_stock_mutation_then_exception_promotes_to_btc_mutation_guard(self):
        def failing_mutating_equity_runner(*, env, now):
            self.btc.write_bytes(b"changed-before-exception")
            self.btc.chmod(0o600)
            raise RuntimeError("fixture failure after mutation")

        result = combined_multimarket_once(
            now=datetime(2026, 9, 30, 15, 7, tzinfo=UTC),
            environ={ROOT_ENV: str(self.root)},
            btc_root=self.root,
            btc_crypto_runner=self.healthy_crypto,
            equity_runner=failing_mutating_equity_runner,
        )
        self.assertEqual(
            result["equity_status"],
            "FAILED_BTC_EVIDENCE_MUTATION_GUARD",
        )
        self.assertEqual(
            result["equity_failure_class"],
            "BtcEvidenceFingerprintMismatch",
        )
        self.assertTrue(result["btc_evidence_changed_during_equity_stage"])
        self.assertFalse(result["original_BTC_status_preserved"])

    def test_unhealthy_btc_skips_stock_sidecar_entirely(self):
        called = []

        def unhealthy(**kwargs):
            return {
                "btc_status": "BLOCKED_ORIGINAL_BTC_CRON_EXCEPTION",
                "sidecar_status": "NOT_RUN",
            }

        def equity_runner(**kwargs):
            called.append(True)
            return {"status": "SHOULD_NOT_RUN"}

        result = combined_multimarket_once(
            now=datetime(2026, 9, 30, 15, 7, tzinfo=UTC),
            environ={ROOT_ENV: str(self.root)},
            btc_root=self.root,
            btc_crypto_runner=unhealthy,
            equity_runner=equity_runner,
        )
        self.assertEqual(result["equity_status"], "SKIPPED_BTC_NOT_HEALTHY")
        self.assertEqual(called, [])

    def test_crypto_integrity_failure_blocks_stock_even_when_btc_status_is_healthy(self):
        called = []

        def crypto_guard_failed(**kwargs):
            return {
                "btc_status": "SAFE_NO_NEW_OBSERVATION",
                "sidecar_status": "FAILED_BTC_EVIDENCE_MUTATION_GUARD",
                "btc_evidence_changed_during_sidecar_stage": True,
            }

        def equity_runner(**kwargs):
            called.append(True)
            return {"status": "SHOULD_NOT_RUN"}

        result = combined_multimarket_once(
            now=datetime(2026, 9, 30, 15, 7, tzinfo=UTC),
            environ={ROOT_ENV: str(self.root)},
            btc_root=self.root,
            btc_crypto_runner=crypto_guard_failed,
            equity_runner=equity_runner,
        )
        self.assertEqual(
            result["equity_status"],
            "SKIPPED_BTC_INTEGRITY_NOT_PROVEN",
        )
        self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()

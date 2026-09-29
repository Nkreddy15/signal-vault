"""No broker/network/Keychain access. Pure fake reader tests + missing-path smoke."""
import json
import tempfile
import unittest
from pathlib import Path

from signal_vault.phase3_readiness import assess_offline_readiness, main


COLLECTOR = {
    "kind": "UNATTENDED_FORWARD_LOCAL_STATUS",
    "state": "ARCHIVED_INTERNAL_EVIDENCE_VERIFIED",
    "broker_order_submission": "DISABLED",
    "network_requests": "NONE",
    "prospective_observations_verified": 1,
    "latest_tick": {"decision": "ONE_NEW_PROSPECTIVE_CANDLE_RECORDED"},
}
LEDGER = {
    "status": "READ_ONLY_PREFLIGHT_OK",
    "mode": "ALPACA_PAPER_ONLY",
    "operator_halted": False,
    "provider_lookup_required": False,
    "unresolved_paper_orders": 0,
    "paper_order_post_enabled": False,
    "authenticated_provider_read_performed": False,
    "live_trading_available": False,
    "sqlite_wal": True,
}


class Phase3OfflineReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.forward = root / "forward"
        self.db = root / "paper.sqlite3"
        # The fake reader may only be called when a file already exists.
        self.db.write_bytes(b"FAKE, NOT OPENED BY A REAL DATABASE READER")
        self.collector = dict(COLLECTOR)
        self.ledger = dict(LEDGER)

    def report(self):
        return assess_offline_readiness(
            forward_root=self.forward, paper_db=self.db,
            collector_reader=lambda **_: self.collector,
            paper_reader=lambda _: self.ledger,
        )

    def test_fake_readers_show_local_prechecks_not_order_authorization(self):
        initial = self.db.read_bytes()
        report = self.report()
        self.assertEqual(report["local_engineering_prechecks"],
                         "PASSED_NOT_TRADE_AUTHORIZATION")
        self.assertEqual(report["collector"]["prospective_observations_verified"], 1)
        self.assertEqual(report["paper_journal"]["status"],
                         "CLEAN_LOCAL_LEDGER_NOT_PROVIDER_ATTESTED")
        self.assertEqual(len(report["blockers"]), 3)
        self.assertIn("SEPARATE_PAPER_ACCOUNT_GET_RESULT_NOT_TRACKED_BY_OFFLINE_REPORT",
                      report["blockers"])
        self.assertIn("SUPERVISED_PAPER_ORDER_RESULT_NOT_TRACKED_BY_OFFLINE_REPORT",
                      report["blockers"])
        self.assertNotIn("SUPERVISED_PAPER_ORDER_NOT_SEPARATELY_AUTHORIZED",
                         report["blockers"])
        self.assertEqual(report["provider_account_check_scope"],
                         "NOT_PERFORMED_IN_THIS_OFFLINE_INVOCATION")
        self.assertEqual(report["separate_provider_get_receipt"],
                         "NOT_TRACKED_BY_THIS_REPORT")
        self.assertFalse(report["paper_order_post_attempted"])
        self.assertFalse(report["credentials_accessed"])
        self.assertFalse(report["provider_trading_account_checked"])
        self.assertEqual(report["broker_order_submission"], "DISABLED")
        self.assertEqual(report["network_requests"], "NONE")
        self.assertEqual(self.db.read_bytes(), initial)
        self.assertFalse(self.forward.exists())  # fake readers never create it

    def test_first_bootstrap_is_not_one_real_automated_observation(self):
        self.collector = {
            **COLLECTOR, "prospective_observations_verified": 0,
            "latest_tick": {"decision": "FIRST_AUTO_SEGMENT_BOOTSTRAPPED"},
        }
        report = self.report()
        self.assertEqual(report["collector"]["status"],
                         "BOOTSTRAP_ONLY_NEXT_CONSECUTIVE_TICK_REQUIRED")
        self.assertEqual(report["local_engineering_prechecks"], "INCOMPLETE")

    def test_halt_receipt_blocks_even_with_an_old_verified_history(self):
        self.collector = {
            **COLLECTOR, "prospective_observations_verified": 3,
            "latest_tick": {"decision": "HALT_PRESERVE_ALL_ORIGINAL_EVIDENCE"},
        }
        report = self.report()
        self.assertEqual(report["collector"]["status"], "HALTED_REQUIRES_OPERATOR_REVIEW")
        self.assertEqual(report["local_engineering_prechecks"], "INCOMPLETE")

    def test_unresolved_and_halted_local_orders_block(self):
        self.ledger = {**LEDGER, "provider_lookup_required": True,
                       "unresolved_paper_orders": 1}
        self.assertEqual(self.report()["paper_journal"]["status"],
                         "UNRESOLVED_ORDER_REQUIRES_PROVIDER_RECONCILIATION")
        self.ledger = {**LEDGER, "operator_halted": True}
        self.assertEqual(self.report()["paper_journal"]["status"], "OPERATOR_HALTED")

    def test_unsafe_preflight_claim_does_not_promote(self):
        self.ledger = {**LEDGER, "paper_order_post_enabled": True}
        result = self.report()
        self.assertEqual(result["paper_journal"]["status"], "INVALID_OR_UNSAFE_PREFLIGHT")
        self.assertEqual(result["local_engineering_prechecks"], "INCOMPLETE")

    def test_bad_collector_schema_or_malformed_tick_is_not_verified(self):
        self.collector = {**COLLECTOR, "broker_order_submission": "ENABLED"}
        self.assertEqual(self.report()["collector"]["status"], "INVALID_STATUS")
        self.collector = {**COLLECTOR, "latest_tick": {"decision": ["bad", "receipt"]}}
        self.assertEqual(self.report()["collector"]["latest_tick_decision"],
                         "NONE_OR_UNRECOGNIZED")
        self.assertEqual(self.report()["local_engineering_prechecks"], "INCOMPLETE")
        self.collector = {**COLLECTOR, "prospective_observations_verified": True}
        self.assertEqual(self.report()["collector"]["status"], "INVALID_STATUS")

    def test_exception_messages_are_never_returned_or_serialized(self):
        secret = "SENTINEL_DO_NOT_PRINT"
        def fail_collector(**_):
            raise RuntimeError(secret)
        def fail_paper(_):
            raise RuntimeError(secret)
        report = assess_offline_readiness(
            forward_root=self.forward, paper_db=self.db,
            collector_reader=fail_collector, paper_reader=fail_paper)
        output = json.dumps(report)
        self.assertNotIn(secret, output)
        self.assertEqual(report["collector"]["error_class"], "RuntimeError")
        self.assertEqual(report["paper_journal"]["error_class"], "RuntimeError")
        self.assertEqual(report["local_engineering_prechecks"], "INCOMPLETE")

    def test_absent_local_paths_remain_absent_in_default_cli(self):
        self.db.unlink()
        # This uses actual local read-only functions on completely missing paths.
        report = assess_offline_readiness(forward_root=self.forward, paper_db=self.db)
        self.assertEqual(report["collector"]["status"],
                         "AWAITING_FIRST_SCHEDULED_TICK")
        self.assertEqual(report["paper_journal"]["status"], "NOT_INITIALIZED")
        self.assertFalse(self.db.exists())
        self.assertFalse(self.forward.exists())


if __name__ == "__main__":
    unittest.main()

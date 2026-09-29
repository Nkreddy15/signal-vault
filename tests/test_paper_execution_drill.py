"""Synthetic-only execution acceptance; no real Alpaca or local persistent state."""
import contextlib
import io
import json
import unittest
from unittest.mock import patch

from signal_vault.paper_execution_drill import main, run_offline_execution_drill


class OfflinePaperExecutionDrillTests(unittest.TestCase):
    def test_full_drill_uses_only_fake_in_memory_transports(self):
        def forbidden_network(*_args, **_kwargs):
            self.fail("real HTTP transport was reached in synthetic drill")
        with patch("signal_vault.paper_executor.build_opener", side_effect=forbidden_network), (
             patch("signal_vault.alpaca_paper.build_opener", side_effect=forbidden_network)):
            result = run_offline_execution_drill()
        self.assertEqual(result["result"], "PASS_FAKE_PROVIDER_STATE_TRANSITIONS_ONLY")
        self.assertEqual(result["scenarios_passed"], 5)
        self.assertEqual(result["injected_fake_transport_attempts"], 4)
        self.assertEqual(len(result["scenarios"]), 5)
        self.assertTrue(all(v == "PASS" for v in result["scenarios"].values()))
        self.assertEqual(result["network_requests"], "NONE")
        self.assertEqual(result["actual_paper_order_posts"], "NONE")
        self.assertEqual(result["database"], "FRESH_IN_MEMORY_SQLITE_PER_SCENARIO")
        self.assertEqual(result["provider_account_access"], "NONE")
        self.assertEqual(result["credentials"], "FAKE_LITERALS_ONLY")
        self.assertEqual(result["live_orders"], "DISABLED")
        self.assertFalse(result["installed_mac_observer_modified"])

    def test_public_cli_emits_only_explicit_synthetic_disclosure(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = main()
        self.assertEqual(rc, 0)
        result = json.loads(output.getvalue())
        self.assertIn("SYNTHETIC", result["kind"])
        self.assertIn("NOT an Alpaca paper order", result["warning"])
        self.assertNotIn("synthetic-paper-secret", output.getvalue())
        self.assertEqual(result["actual_paper_order_posts"], "NONE")

    def test_any_internal_failure_is_redacted_and_nonzero(self):
        output = io.StringIO()
        with patch("signal_vault.paper_execution_drill.run_offline_execution_drill",
                   side_effect=RuntimeError("SENTINEL_SECRET_NEVER_EMIT")), (
             contextlib.redirect_stdout(output)):
            rc = main()
        self.assertEqual(rc, 2)
        result = json.loads(output.getvalue())
        self.assertEqual(result["result"], "FAIL_CLOSED")
        self.assertEqual(result["failure_class"], "RuntimeError")
        self.assertNotIn("SENTINEL_SECRET_NEVER_EMIT", output.getvalue())
        self.assertEqual(result["actual_paper_order_posts"], "NONE")


if __name__ == "__main__":
    unittest.main()

"""Persistent synthetic restart/partial-fill acceptance has no real provider I/O."""
from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from signal_vault.paper_restart_fault_drill import (
    main,run_persistent_restart_partial_fault_drill,
)


class PersistentPaperRestartFaultDrillTests(unittest.TestCase):
    def test_two_restarts_partial_progress_terminal_immutability_and_zero_POST(self):
        def forbidden_network(*_args,**_kwargs):
            self.fail("real HTTP reached offline restart fault drill")
        with patch("signal_vault.paper_executor.build_opener",
                   side_effect=forbidden_network), patch(
             "signal_vault.alpaca_paper.build_opener",
             side_effect=forbidden_network):
            result=run_persistent_restart_partial_fault_drill()
        self.assertEqual(
            result["result"],
            "PASS_SYNTHETIC_PERSISTENT_FAILURE_SEMANTICS_ONLY")
        self.assertEqual(result["durable_restart_count"],2)
        self.assertEqual(result["fake_POST_attempts"],0)
        self.assertEqual(result["fake_GET_attempts"],2)
        self.assertFalse(result["terminal_reconciliation_performed"])
        self.assertEqual(result["reservation_retained_usd"],"15")
        self.assertFalse(result["new_execution_unblocked"])
        self.assertEqual(result["network_requests"],"NONE")
        self.assertEqual(result["provider_account_access"],"NONE")
        self.assertEqual(result["actual_paper_order_posts"],"NONE")
        self.assertEqual(result["automatic_paper_trading"],"DISABLED")
        self.assertEqual(result["live_trading"],"UNAVAILABLE")

    def test_cli_redacts_internal_failure_and_remains_no_order(self):
        output=io.StringIO()
        with patch(
            "signal_vault.paper_restart_fault_drill.run_persistent_restart_partial_fault_drill",
            side_effect=RuntimeError("SECRET_SENTINEL")),
             contextlib.redirect_stdout(output):
            rc=main()
        self.assertEqual(rc,2)
        body=json.loads(output.getvalue())
        self.assertEqual(body["result"],"FAIL_CLOSED")
        self.assertEqual(body["failure_class"],"RuntimeError")
        self.assertNotIn("SECRET_SENTINEL",output.getvalue())
        self.assertEqual(body["actual_paper_order_posts"],"NONE")
        self.assertEqual(body["automatic_paper_trading"],"DISABLED")

    def test_cli_success_is_explicitly_synthetic(self):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            rc=main()
        self.assertEqual(rc,0)
        body=json.loads(output.getvalue())
        self.assertIn("SYNTHETIC",body["result"])
        self.assertIn("NOT an Alpaca order",body["warning"])
        self.assertEqual(body["fake_POST_attempts"],0)


if __name__=="__main__":
    unittest.main()

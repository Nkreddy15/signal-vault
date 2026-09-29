"""Review-only contract: automatically triggered historical replay has NO DATA keys."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class KeylessMergedMainSensitivityTests(unittest.TestCase):
    def test_exact_two_previously_authorized_history_runs_only_and_no_provider_keys(self):
        workflow=(ROOT/".github"/"workflows"/
                  "offline-12-market-allocation-sensitivity.yml").read_text(
                      encoding="utf-8")
        trigger=workflow.split("\non:\n",1)[1].split("\npermissions:\n",1)[0]
        self.assertIn("push:",trigger)
        self.assertIn("main",trigger)
        self.assertNotIn("workflow_dispatch:",trigger)
        self.assertNotIn("schedule:",trigger)
        self.assertIn("actions: read",workflow)
        self.assertIn("contents: read",workflow)
        self.assertIn("github.event_name == 'push'",workflow)
        self.assertIn("github.ref == 'refs/heads/main'",workflow)
        self.assertIn("36647061726",workflow)
        self.assertIn("36637836735",workflow)
        self.assertIn("--allocation-sensitivity",workflow)
        self.assertIn("retention-days: 7",workflow)
        for invalid in (
            "secrets.SIGNAL_VAULT_RESEARCH_DATA_SECRET",
            "SIGNAL_VAULT_FORWARD_DATA_KEY_ID",
            "SIGNAL_VAULT_ENABLE_PAPER_ORDERS",
            "https://data.alpaca.markets",
            "api.alpaca.markets",
            "workflow_dispatch:",
            "schedule:",
        ):
            self.assertNotIn(invalid,workflow)
        self.assertIn("if-no-files-found: error",workflow)
        self.assertNotIn("railway",workflow.lower())


if __name__=="__main__":
    unittest.main()

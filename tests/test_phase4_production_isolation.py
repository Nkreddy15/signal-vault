"""Prevent offline multi-asset research code from leaking into production cron."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

from signal_vault.shared_research_book import SharedResearchLimits

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"src"/"signal_vault"


class ProductionIsolationTests(unittest.TestCase):
    def test_cloud_runtime_and_btc_capture_cannot_import_offline_expansion(self):
        forbidden={
            "multi_asset_historical","multi_asset_research_cli",
            "multi_asset_simulation","multi_asset_shadow_scan",
            "research_universe","shared_research_book",
            "offline_multimarket_pipeline","ci_historical_crypto",
        }
        for filename in (
            "railway_forward_cron.py","cloud_forward_service.py",
            "unattended_forward_cycle.py","forward_capture.py",
        ):
            code=(SRC/filename).read_text(encoding="utf-8")
            tree=ast.parse(code)
            imported=set()
            for node in ast.walk(tree):
                if isinstance(node,ast.ImportFrom) and node.module:
                    imported.add(node.module.rsplit(".",1)[-1])
                elif isinstance(node,ast.Import):
                    imported.update(a.name.rsplit(".",1)[-1] for a in node.names)
            self.assertFalse(
                forbidden & imported,
                f"{filename} unexpectedly imported Phase 4 historical code")

    def test_manual_historical_workflow_is_never_automatic_or_trade_enabled(self):
        content=(ROOT/".github"/"workflows"/
                 "manual-historical-crypto-research.yml").read_text(encoding="utf-8")
        trigger=content.split("\non:\n",1)[1].split("\npermissions:\n",1)[0]
        self.assertIn("workflow_dispatch:",trigger)
        for not_allowed in ("push:","pull_request:","schedule:","workflow_run:"):
            self.assertNotIn("\n  "+not_allowed,trigger)
        self.assertIn("if: github.repository == 'Nkreddy15/signal-vault'",content)
        self.assertIn("github.ref == 'refs/heads/main'",content)
        self.assertIn("permissions:\n  contents: read",content)
        self.assertNotIn("SIGNAL_VAULT_ENABLE_PAPER_ORDERS: true",content)
        self.assertIn("retention-days: 7",content)

    def test_shared_sandbox_caps_remain_explicit_not_twelve_separate_100s(self):
        limits=SharedResearchLimits()
        self.assertEqual(limits.initial_bankroll_usd,100)
        self.assertEqual(limits.single_buy_usd,15)
        self.assertEqual(limits.maximum_total_long_exposure_usd,30)
        self.assertEqual(limits.daily_loss_cap_usd,3)
        self.assertEqual(limits.peak_drawdown_cap_usd,10)


if __name__=="__main__":
    unittest.main()

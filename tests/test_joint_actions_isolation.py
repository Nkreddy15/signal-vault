"""Safety/activation contract of the optional second historical Actions job."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class SeparateKeylessTwelveMarketActionsTests(unittest.TestCase):
    def test_only_explicit_operator_September_six_asset_run_triggers_joint_job(self):
        path=ROOT/".github"/"workflows"/"manual-historical-crypto-research.yml"
        workflow=path.read_text(encoding="utf-8")
        trigger=workflow.split("\non:\n",1)[1].split("\npermissions:\n",1)[0]
        self.assertIn("workflow_dispatch:",trigger)
        for unauthorized in ("push:","schedule:","pull_request:","workflow_run:"):
            self.assertNotIn("\n  "+unauthorized,trigger)
        before,second=workflow.split(
            "\n  paired-stocks-twelve-asset-offline-research:",1)
        self.assertIn("needs: historical-get-only",second)
        self.assertIn("inputs.start_utc == '2026-09-14T00:00:00Z'",second)
        self.assertIn("inputs.end_utc == '2026-09-26T00:00:00Z'",second)
        self.assertIn(
            "inputs.symbols == 'BTC/USD ETH/USD SOL/USD LTC/USD LINK/USD AVAX/USD'",
            second)
        self.assertIn("github.ref == 'refs/heads/main'",second)
        self.assertIn("actions: read",second)
        self.assertIn("stock-IEX-history",second)
        self.assertIn("36637836735",second)
        self.assertIn("python -m signal_vault.joint_historical_source",second)
        self.assertIn("retention-days: 7",second)

    def test_manual_workflow_defaults_match_automatic_join_guard_exactly(self):
        # September run 36640599885 passed its July/Aug source GET but
        # silently skipped the mixed-market job because the dates retained
        # obsolete defaults. Catch ANY future drift between the green Run
        # workflow form and the actual second-job gate before deployment.
        workflow=(ROOT/".github"/"workflows"/
                  "manual-historical-crypto-research.yml").read_text(
                      encoding="utf-8")
        declared=workflow.split("\non:\n",1)[1].split("\npermissions:\n",1)[0]
        before,gate=workflow.split(
            "\n  paired-stocks-twelve-asset-offline-research:",1)
        expected={
            "start_utc":"2026-09-14T00:00:00Z",
            "end_utc":"2026-09-26T00:00:00Z",
            "symbols":"BTC/USD ETH/USD SOL/USD LTC/USD LINK/USD AVAX/USD",
        }
        for key,value in expected.items():
            section=declared.split("\n      "+key+":",1)[1].split(
                "\n      ",1)[0]
            self.assertIn('default: "'+value+'"',section)
            self.assertIn("inputs."+key+" == '"+value+"'",gate)
        self.assertIn(
            '- "BTC/USD ETH/USD SOL/USD LTC/USD LINK/USD AVAX/USD"',
            declared)
        self.assertIn("needs: historical-get-only",gate)
        self.assertIn("github.ref == 'refs/heads/main'",gate)
        self.assertIn("github.event_name == 'workflow_dispatch'",gate)
        self.assertNotIn("secrets.SIGNAL_VAULT_RESEARCH_DATA_SECRET",gate)

    def test_only_first_job_reads_alpaca_DATA_secrets(self):
        workflow=(ROOT/".github"/"workflows"/
                  "manual-historical-crypto-research.yml").read_text(encoding="utf-8")
        first,second=workflow.split(
            "\n  paired-stocks-twelve-asset-offline-research:",1)
        self.assertIn("secrets.SIGNAL_VAULT_RESEARCH_DATA_KEY_ID",first)
        self.assertIn("secrets.SIGNAL_VAULT_RESEARCH_DATA_SECRET",first)
        self.assertNotIn("SIGNAL_VAULT_RESEARCH_DATA_KEY_ID",second)
        self.assertNotIn("SIGNAL_VAULT_RESEARCH_DATA_SECRET",second)
        self.assertNotIn("https://data.alpaca.markets",second)
        self.assertNotIn("api.alpaca.markets",second)
        self.assertIn("no Alpaca SDK",second)
        self.assertNotIn("ALPACA_LIVE_KEY",second)


if __name__=="__main__":
    unittest.main()

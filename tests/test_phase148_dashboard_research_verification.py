import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path
import tempfile

from signal_vault import railway_all_markets_research_cron as cron


class Phase148DashboardResearchVerificationTests(unittest.TestCase):
    @patch.object(cron,"archive_dashboard_snapshot")
    @patch.object(cron,"build_dashboard_snapshot")
    @patch.object(cron,"all_market_forward_status")
    @patch.object(cron,"fingerprint_btc_evidence_tree")
    @patch.object(cron,"_kalshi_storage_budget")
    def test_cron_reports_archived_research_status_without_enabling_paper(
        self,budget,fingerprint,status,dashboard,archive
    ):
        fingerprint.return_value={"tree_sha256":"same"}
        budget.return_value={"available_bytes_before_kalshi":999999999,"existing_kalshi_evidence_bytes":0}
        status.return_value={"kind":"x"}
        dashboard.return_value={
            "strategy_research":{
                "status":"BLOCKED_NO_LOW_CHURN_CANDIDATE",
                "candidate_family":"CRYPTO_90DAY_LOW_CHURN_CROSS_SECTIONAL_RESEARCH_RECEIPT",
                "selected_strategy":None,
                "paper_activation_permitted":False,
            }
        }
        archive.return_value=Path("dashboard.json")
        core=lambda **kwargs:{
            "crypto_btc_status":"SAFE_NO_NEW_OBSERVATION",
            "equity_status":"EVIDENCE_PRESENT",
            "btc_evidence_changed_during_equity_stage":False,
        }
        kalshi=lambda **kwargs:{"status":"EVIDENCE_PRESENT"}
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            root.chmod(0o700)
            out=cron.combined_all_markets_once(
                now=datetime(2026,10,1,tzinfo=timezone.utc),
                environ={},
                btc_root=root,
                core_runner=core,
                kalshi_runner=kalshi,
            )
        self.assertEqual(out["dashboard_snapshot_status"],"AVAILABLE")
        self.assertEqual(
            out["dashboard_strategy_research_status"],
            "BLOCKED_NO_LOW_CHURN_CANDIDATE",
        )
        self.assertFalse(out["dashboard_strategy_research_paper_activation_permitted"])
        self.assertEqual(out["paper_order_submission"],"DISABLED")
        self.assertEqual(out["live_trading"],"UNAVAILABLE")


if __name__=="__main__":
    unittest.main()

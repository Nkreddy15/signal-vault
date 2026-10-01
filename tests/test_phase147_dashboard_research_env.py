import json
import unittest
from unittest.mock import patch

from signal_vault.all_market_dashboard import build_dashboard_snapshot


class Phase147DashboardResearchEnvTests(unittest.TestCase):
    def _status(self):
        return {
            "checked_at_utc":"2026-10-01T00:00:00+00:00",
            "btc_and_six_crypto":{},
            "us_equity":{},
            "kalshi":{},
            "lane_next_actions":{
                "six_crypto":"x","us_equity":"y","kalshi":"z",
            },
        }

    def _runway(self):
        return {
            "current_forward_evidence_blockers":[],
            "all_market_forward_source_and_review_stages_complete":False,
        }

    @patch("signal_vault.all_market_dashboard.paper_runway_from_forward_status")
    @patch("signal_vault.all_market_dashboard.all_market_forward_status")
    def test_missing_env_is_not_imported(self,status,runway):
        status.return_value=self._status()
        runway.return_value=self._runway()
        out=build_dashboard_snapshot(root=__import__("pathlib").Path("."),environ={})
        self.assertEqual(out["strategy_research"]["status"],"NOT_IMPORTED")

    @patch("signal_vault.all_market_dashboard.paper_runway_from_forward_status")
    @patch("signal_vault.all_market_dashboard.all_market_forward_status")
    def test_valid_env_receipt_populates_panel(self,status,runway):
        status.return_value=self._status()
        runway.return_value=self._runway()
        receipt={
            "kind":"CRYPTO_90DAY_LOW_CHURN_CROSS_SECTIONAL_RESEARCH_RECEIPT",
            "status":"BLOCKED_NO_LOW_CHURN_CANDIDATE",
            "selected_strategy":None,
            "paper_activation_permitted":False,
            "new_prospective_confirmation_required":True,
            "broker_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
            "results":{},
        }
        out=build_dashboard_snapshot(
            root=__import__("pathlib").Path("."),
            environ={"SIGNAL_VAULT_CRYPTO_RESEARCH_RECEIPT_JSON":json.dumps(receipt)},
        )
        self.assertEqual(
            out["strategy_research"]["status"],
            "BLOCKED_NO_LOW_CHURN_CANDIDATE",
        )
        self.assertFalse(out["strategy_research"]["paper_activation_permitted"])

    @patch("signal_vault.all_market_dashboard.paper_runway_from_forward_status")
    @patch("signal_vault.all_market_dashboard.all_market_forward_status")
    def test_execution_enabled_env_receipt_fails_closed(self,status,runway):
        status.return_value=self._status()
        runway.return_value=self._runway()
        receipt={
            "kind":"CRYPTO_90DAY_LOW_CHURN_CROSS_SECTIONAL_RESEARCH_RECEIPT",
            "status":"BAD",
            "broker_order_submission":"ENABLED",
            "live_trading":"UNAVAILABLE",
        }
        with self.assertRaises(ValueError):
            build_dashboard_snapshot(
                root=__import__("pathlib").Path("."),
                environ={"SIGNAL_VAULT_CRYPTO_RESEARCH_RECEIPT_JSON":json.dumps(receipt)},
            )


if __name__=="__main__":
    unittest.main()

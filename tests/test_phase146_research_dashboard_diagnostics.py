import json
from pathlib import Path
import tempfile
import unittest

from signal_vault.research_dashboard_diagnostics import read_crypto_research_diagnostics


class Phase146ResearchDashboardDiagnosticsTests(unittest.TestCase):
    def test_missing_receipt_is_explicitly_not_imported(self):
        out=read_crypto_research_diagnostics(None)
        self.assertEqual(out["status"],"NOT_IMPORTED")
        self.assertIsNone(out["selected_strategy"])

    def test_private_low_churn_receipt_exposes_metrics_without_execution(self):
        receipt={
            "kind":"CRYPTO_90DAY_LOW_CHURN_CROSS_SECTIONAL_RESEARCH_RECEIPT",
            "status":"BLOCKED_NO_LOW_CHURN_CANDIDATE",
            "selected_strategy":None,
            "paper_activation_permitted":False,
            "new_prospective_confirmation_required":True,
            "broker_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
            "results":{
                "candidate-a":{
                    "illustrative_base_friction":{
                        "development":{
                            "net_marked_pnl_usd":"1.2",
                            "passive_equal_weight_marked_pnl_usd":"1.0",
                            "fill_count":4,
                            "max_marked_drawdown_usd":"0.8",
                        }
                    }
                }
            },
        }
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"receipt.json"
            p.write_text(json.dumps(receipt))
            p.chmod(0o600)
            out=read_crypto_research_diagnostics(p)
        self.assertEqual(out["status"],"BLOCKED_NO_LOW_CHURN_CANDIDATE")
        self.assertFalse(out["paper_activation_permitted"])
        self.assertTrue(out["new_prospective_confirmation_required"])
        self.assertEqual(out["base_friction_rows"][0]["alpha_vs_passive_usd"],"0.2")

    def test_public_or_execution_enabled_receipt_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"receipt.json"
            p.write_text(json.dumps({
                "kind":"CRYPTO_90DAY_LOW_CHURN_CROSS_SECTIONAL_RESEARCH_RECEIPT",
                "status":"BAD",
                "broker_order_submission":"ENABLED",
                "live_trading":"UNAVAILABLE",
            }))
            p.chmod(0o600)
            with self.assertRaises(ValueError):
                read_crypto_research_diagnostics(p)


if __name__=="__main__":
    unittest.main()

import unittest

from signal_vault.all_market_dashboard import KIND, _pct, render_dashboard_html


class OperatorDashboardProgressTests(unittest.TestCase):
    def test_pct_is_bounded_and_deterministic(self):
        self.assertEqual(_pct(0,10),0)
        self.assertEqual(_pct(5,10),50)
        self.assertEqual(_pct(15,10),100)
        self.assertEqual(_pct(-1,10),0)
        self.assertEqual(_pct("bad",10),0)

    def test_render_includes_progress_meters_without_enabling_execution(self):
        snapshot={
            "kind":KIND,
            "checked_at_utc":"2026-10-01T18:00:00+00:00",
            "lanes":{
                "six_crypto":{
                    "prospective_source_hours":31,
                    "fully_scored_outcomes":30,
                    "source_hours_remaining":138,
                    "scored_outcomes_remaining":138,
                    "source_progress_pct":18,
                    "score_progress_pct":18,
                    "next_action":"CONTINUE_UNATTENDED_FORWARD_COLLECTION",
                },
                "us_equity":{
                    "session_plans":1,
                    "core_hour_receipts":3,
                    "session_plans_remaining":9,
                    "core_hour_receipts_remaining":57,
                    "capture_windows_open":0,
                    "session_progress_pct":10,
                    "core_hour_progress_pct":5,
                    "next_action":"CONTINUE_UNATTENDED_STOCK_FORWARD_COLLECTION",
                },
                "kalshi":{
                    "plan_present":False,
                    "planned_markets":None,
                    "decision_snapshots":0,
                    "settlements":0,
                    "decision_snapshots_remaining":40,
                    "settlements_remaining":20,
                    "decision_progress_pct":0,
                    "settlement_progress_pct":0,
                    "next_action":"PRECOMMIT_PUBLIC_KALSHI_PROSPECTIVE_PLAN_GET_ONLY",
                },
            },
            "paper_runway_blockers":["FORWARD_EVIDENCE_INCOMPLETE"],
            "paper_order_submission":"DISABLED",
            "demo_order_submission":"DISABLED",
            "live_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        }
        html=render_dashboard_html(snapshot).decode("utf-8")
        self.assertIn('value="18"',html)
        self.assertIn('value="10"',html)
        self.assertIn("PAPER: DISABLED",html)
        self.assertIn("LIVE: UNAVAILABLE",html)
        self.assertIn("Current forward blockers",html)
        self.assertNotIn("<script",html.lower())


if __name__=="__main__":
    unittest.main()

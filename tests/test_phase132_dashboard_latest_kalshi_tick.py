import unittest

from signal_vault.all_market_dashboard import KIND, render_dashboard_html
from signal_vault.railway_all_markets_research_cron import _kalshi_tick_for_dashboard


class KalshiDashboardTickTests(unittest.TestCase):
    def test_runtime_tick_is_allowlisted_for_dashboard(self):
        output={
            "kalshi_status":"PLANNING_BLOCKED_FAIL_CLOSED",
            "kalshi":{
                "status":"PLANNING_BLOCKED_FAIL_CLOSED",
                "planning_failure_code":"INSUFFICIENT_ELIGIBLE_FUTURE_MARKETS",
                "public_get_requests_used":3,
                "public_get_budget":25,
                "credentials_accessed":"NONE",
                "secret":"must-not-leak",
            },
        }
        item=_kalshi_tick_for_dashboard(output)
        self.assertEqual(
            item["planning_failure_code"],
            "INSUFFICIENT_ELIGIBLE_FUTURE_MARKETS",
        )
        self.assertEqual(item["public_get_requests_used"],3)
        self.assertNotIn("secret",item)
        self.assertNotIn("credentials_accessed",item)

    def test_dashboard_renders_latest_kalshi_tick(self):
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
                    "next_action":"CONTINUE",
                },
                "us_equity":{
                    "session_plans":1,
                    "core_hour_receipts":3,
                    "session_plans_remaining":9,
                    "core_hour_receipts_remaining":57,
                    "capture_windows_open":0,
                    "session_progress_pct":10,
                    "core_hour_progress_pct":5,
                    "next_action":"CONTINUE",
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
                    "next_action":"PLAN",
                },
            },
            "latest_kalshi_tick":{
                "status":"PLANNING_BLOCKED_FAIL_CLOSED",
                "planning_failure_code":"MALFORMED_PUBLIC_EVENT_DISCOVERY",
                "public_get_requests_used":18,
                "public_get_budget":25,
            },
            "paper_runway_blockers":[],
        }
        html=render_dashboard_html(snapshot).decode("utf-8")
        self.assertIn("Latest Kalshi Tick",html)
        self.assertIn("MALFORMED_PUBLIC_EVENT_DISCOVERY",html)
        self.assertIn(">18<",html)
        self.assertNotIn("<script",html.lower())


if __name__=="__main__":
    unittest.main()

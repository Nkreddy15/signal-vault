import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from signal_vault.ci_historical_equities import execute_manual_equity_history
from signal_vault.ci_long_equity_history import (
    APPROVAL,
    execute_long_equity_history,
)
from signal_vault.offline_long_equity_validation import (
    validate_long_equity_history,
)
from test_ci_historical_equities import FakeLiquidIEXProvider

NOW = datetime(2026, 9, 30, 19, 40, tzinfo=timezone.utc)
ENV = {
    "GITHUB_ACTIONS": "true",
    "GITHUB_EVENT_NAME": "workflow_dispatch",
    "GITHUB_REPOSITORY": "Nkreddy15/signal-vault",
    "GITHUB_REF": "refs/heads/main",
    "SIGNAL_VAULT_LONG_EQUITY_READ_APPROVED": APPROVAL,
    "SIGNAL_VAULT_LONG_EQUITY_START_DATE": "2026-07-01",
    "SIGNAL_VAULT_LONG_EQUITY_END_DATE_EXCLUSIVE": "2026-08-31",
    "SIGNAL_VAULT_RESEARCH_DATA_KEY_ID": "FIXTURE_NEVER_REAL_KEY",
    "SIGNAL_VAULT_RESEARCH_DATA_SECRET": "FIXTURE_NEVER_REAL_SECRET",
}


class LongEquityOfflineValidationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "long"
        FakeLiquidIEXProvider.instances = []
        FakeLiquidIEXProvider.drop_session = None

    @staticmethod
    def fake_runner(*, env, as_of, output_folder):
        return execute_manual_equity_history(
            env=env,
            as_of=as_of,
            provider_factory=FakeLiquidIEXProvider,
            output_folder=output_folder,
        )

    def build_source(self):
        result = execute_long_equity_history(
            env=ENV,
            as_of=NOW,
            output_root=self.root,
            runner=self.fake_runner,
        )
        self.assertGreater(result["chunk_count"], 1)
        return result

    def test_replays_all_chunks_and_runs_three_fixed_historical_scenarios(self):
        source = self.build_source()
        result = validate_long_equity_history(self.root, as_of=NOW)

        self.assertEqual(result["chunk_count"], source["chunk_count"])
        self.assertGreater(result["source_archive_count"], 20)
        self.assertGreater(result["verified_core_hours_per_asset"], 150)
        self.assertEqual(
            set(result["three_fixed_friction_scenarios"]),
            {
                "illustrative_low_equity_friction",
                "illustrative_base_equity_friction",
                "illustrative_high_equity_friction",
            },
        )
        base = result["three_fixed_friction_scenarios"][
            "illustrative_base_equity_friction"
        ]
        self.assertEqual(
            set(base["assets"]),
            {"AAPL", "AMD", "MSFT", "NVDA", "QQQ", "SPY"},
        )
        self.assertEqual(
            set(base["all_predeclared_shared_bankroll_research_books"]),
            {
                "cash-v1-predeclared",
                "one-allocation-passive-v1-predeclared",
                "generic-ema12x26-v1-predeclared",
                "generic-momentum24bar50bps-v1-predeclared",
            },
        )
        for symbol in base["assets"]:
            folds = base["per_asset_chronological_folds"][symbol]
            for hypothesis in folds.values():
                self.assertEqual(
                    set(hypothesis),
                    {"development", "validation", "untouched_test"},
                )
        self.assertTrue(
            result["chronological_development_validation_untouched_test_complete"]
        )
        self.assertFalse(result["untouched_test_used_for_strategy_selection"])
        self.assertTrue(result["historical_results_are_not_prospective_validation"])
        self.assertFalse(result["historical_walk_forward_complete"])
        self.assertEqual(result["prospective_observations_verified"], 0)
        self.assertEqual(result["broker_order_submission"], "DISABLED")
        self.assertEqual(result["live_trading"], "UNAVAILABLE")
        self.assertNotIn("FIXTURE_NEVER_REAL", json.dumps(result))

    def test_tampered_chunk_report_is_rejected(self):
        self.build_source()
        report = self.root / "chunk-001" / "offline_equity_research.json"
        body = json.loads(report.read_text())
        body["feed"] = "alpaca_equity_sip"
        report.write_text(json.dumps(body))
        report.chmod(0o600)
        with self.assertRaises(ValueError):
            validate_long_equity_history(self.root, as_of=NOW)

    def test_tampered_source_archive_is_rejected(self):
        self.build_source()
        archive = next((self.root / "chunk-001").glob("historical-us_equity-*.json"))
        raw = archive.read_bytes()
        archive.write_bytes(raw + b"\n")
        archive.chmod(0o600)
        with self.assertRaises(ValueError):
            validate_long_equity_history(self.root, as_of=NOW)


if __name__ == "__main__":
    unittest.main()

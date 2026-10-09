from pathlib import Path
import unittest


ROOT=Path(__file__).resolve().parents[1]


class Phase139ReplaySixDayBootstrapTests(unittest.TestCase):
    def test_replay_defaults_to_exact_six_day_source_and_builds_bootstrap_receipt(self):
        workflow=(ROOT/".github"/"workflows"/
                  "manual-replay-crypto-research-v2.yml").read_text()
        self.assertIn('default: "36918820231"',workflow)
        self.assertIn(
            "python -m signal_vault.historical_bootstrap_validation",
            workflow,
        )
        self.assertIn(
            "private-v2-replay/historical_bootstrap_validation.json",
            workflow,
        )
        self.assertIn(
            "private-v2-replay/offline_research_analysis.json",
            workflow,
        )

    def test_replay_remains_data_keyless_and_no_new_market_download(self):
        workflow=(ROOT/".github"/"workflows"/
                  "manual-replay-crypto-research-v2.yml").read_text()
        self.assertNotIn("SIGNAL_VAULT_RESEARCH_DATA_KEY_ID",workflow)
        self.assertNotIn("SIGNAL_VAULT_RESEARCH_DATA_SECRET",workflow)
        self.assertNotIn("ci_historical_crypto",workflow)
        self.assertIn("actions/download-artifact@v4",workflow)
        self.assertIn("python -m signal_vault.ci_replay_history",workflow)


if __name__=="__main__":
    unittest.main()

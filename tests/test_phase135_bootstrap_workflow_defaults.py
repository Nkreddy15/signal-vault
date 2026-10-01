from pathlib import Path
import unittest

from signal_vault.joint_historical_source import _eligible_name


class Phase135BootstrapWorkflowDefaultsTests(unittest.TestCase):
    def test_bootstrap_validation_artifact_is_allowlisted_for_crypto_bundle(self):
        self.assertTrue(
            _eligible_name("historical_bootstrap_validation.json","crypto")
        )
        self.assertFalse(
            _eligible_name("historical_bootstrap_validation.json","us_equity")
        )

    def test_manual_crypto_workflow_defaults_to_exact_six_day_window(self):
        text=Path(".github/workflows/manual-historical-crypto-research.yml").read_text()
        self.assertIn('default: "2026-09-25T18:00:00Z"',text)
        self.assertIn('default: "2026-10-01T18:00:00Z"',text)


if __name__=="__main__":
    unittest.main()

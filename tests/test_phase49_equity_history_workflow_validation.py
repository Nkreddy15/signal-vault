from pathlib import Path
import unittest


class LongEquityWorkflowValidationTests(unittest.TestCase):
    def test_manual_history_workflow_validates_before_upload_and_stays_manual(self):
        text = Path(
            ".github/workflows/manual-long-horizon-equity-research.yml"
        ).read_text()
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("schedule:", text)
        self.assertIn(
            "python -m signal_vault.offline_long_equity_validation",
            text,
        )
        self.assertIn(
            "--source-root private-equity-long-artifacts",
            text,
        )
        self.assertIn(
            "--output private-equity-long-artifacts/offline_long_equity_validation.json",
            text,
        )
        self.assertLess(
            text.index("offline_long_equity_validation"),
            text.index("actions/upload-artifact@v4"),
        )
        self.assertIn("contents: read", text)
        self.assertNotIn("paper-api.alpaca.markets", text)
        self.assertNotIn("/v2/orders", text)
        self.assertNotIn("SIGNAL_VAULT_LIVE", text)


if __name__ == "__main__":
    unittest.main()

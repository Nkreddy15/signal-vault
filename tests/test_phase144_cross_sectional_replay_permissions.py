from pathlib import Path
import unittest


class Phase144CrossSectionalReplayPermissionsTests(unittest.TestCase):
    def test_workflow_relocks_downloaded_artifact_before_review(self):
        text=Path(".github/workflows/manual-replay-90day-cross-sectional-crypto.yml").read_text()
        lock=text.index("Re-lock downloaded historical artifact permissions")
        review=text.index("Run cross-sectional 90-day research review")
        self.assertLess(lock,review)
        self.assertIn("chmod 700 downloaded-history",text)
        self.assertIn("find downloaded-history -type f -exec chmod 600 {} +",text)


if __name__=="__main__":
    unittest.main()

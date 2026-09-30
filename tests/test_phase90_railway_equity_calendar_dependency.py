import unittest
from pathlib import Path


class RailwayEquityCalendarDependencyTests(unittest.TestCase):
    def test_docker_image_installs_equity_research_extra(self):
        dockerfile=Path("Dockerfile").read_text()
        self.assertIn(
            "python -m pip install --no-cache-dir --no-compile '.[equity-research]'",
            dockerfile,
        )
        self.assertNotIn(
            "python -m pip install --no-cache-dir --no-compile . \\",
            dockerfile,
        )


if __name__=="__main__":
    unittest.main()

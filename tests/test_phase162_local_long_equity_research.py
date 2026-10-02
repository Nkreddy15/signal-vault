from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from signal_vault.local_long_equity_research import (
    APPROVAL,
    _parse_dotenv,
    collect_local_long_equity_history,
)


class Phase162LocalLongEquityResearchTests(unittest.TestCase):
    def test_dotenv_is_parsed_as_data_not_shell(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "ALPACA_IS_PAPER=true\n"
                "ALPACA_API_KEY='paper-key'\n"
                'ALPACA_API_SECRET="paper-secret"\n',
                encoding="utf-8",
            )
            values = _parse_dotenv(path)
            self.assertEqual(values["ALPACA_IS_PAPER"], "true")
            self.assertEqual(values["ALPACA_API_KEY"], "paper-key")
            self.assertEqual(values["ALPACA_API_SECRET"], "paper-secret")

    def test_missing_paper_marker_fails_before_provider_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = root / ".env"
            env.write_text(
                "ALPACA_API_KEY=key\nALPACA_API_SECRET=secret\n",
                encoding="utf-8",
            )
            with self.assertRaises(PermissionError):
                collect_local_long_equity_history(
                    env_file=env,
                    start_date=date(2025, 10, 1),
                    end_date_exclusive=date(2026, 9, 30),
                    output_root=root / "output",
                    as_of=datetime(2026, 10, 2, tzinfo=timezone.utc),
                    approval=APPROVAL,
                )
            self.assertFalse((root / "output").exists())

    def test_wrong_approval_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = root / ".env"
            env.write_text(
                "ALPACA_IS_PAPER=true\n"
                "ALPACA_API_KEY=key\n"
                "ALPACA_API_SECRET=secret\n",
                encoding="utf-8",
            )
            with self.assertRaises(PermissionError):
                collect_local_long_equity_history(
                    env_file=env,
                    start_date=date(2025, 10, 1),
                    end_date_exclusive=date(2026, 9, 30),
                    output_root=root / "output",
                    as_of=datetime(2026, 10, 2, tzinfo=timezone.utc),
                    approval="WRONG",
                )


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from signal_vault.alerts import JsonlAlertSink, alert_severity
from signal_vault.paper_runtime import PaperCycleResult


NOW = datetime(2026, 9, 28, 22, tzinfo=timezone.utc)


class AlertTests(unittest.TestCase):
    def test_only_alert_states_emit_and_repeat_is_deduplicated(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "alerts.jsonl"
            sink = JsonlAlertSink(path)
            self.assertFalse(sink.record_if_needed(PaperCycleResult("HOLD", "x"), at=NOW))
            bad = PaperCycleResult("BLOCKED_PROVIDER_DRIFT", "account_id=SECRET")
            self.assertTrue(sink.record_if_needed(bad, at=NOW))
            self.assertFalse(sink.record_if_needed(bad, at=NOW))
            row = json.loads(path.read_text().strip())
            self.assertEqual(row["severity"], "critical")
            self.assertNotIn("SECRET", path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_alert_resets_after_healthy_state(self):
        with tempfile.TemporaryDirectory() as td:
            sink = JsonlAlertSink(Path(td) / "a")
            bad = PaperCycleResult("HOLD_BAD_MARKET_DATA", "x")
            self.assertTrue(sink.record_if_needed(bad, at=NOW))
            self.assertFalse(sink.record_if_needed(PaperCycleResult("HOLD", "ok"), at=NOW))
            self.assertTrue(sink.record_if_needed(bad, at=NOW))

    def test_classification(self):
        self.assertIsNone(alert_severity("HOLD"))
        self.assertEqual(alert_severity("OPERATOR_HALTED"), "info")

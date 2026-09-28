import unittest
from datetime import datetime, timezone

from signal_vault.paper_runtime import PaperCycleResult
from signal_vault.paper_schedule import next_delay_seconds


NOW = datetime(2026, 9, 28, 22, 37, 10, tzinfo=timezone.utc)


class PaperScheduleTests(unittest.TestCase):
    def result(self, state):
        return PaperCycleResult(state, "x")

    def test_provider_lifecycle_is_polled_quickly(self):
        self.assertEqual(next_delay_seconds(self.result("BLOCKED_PROVIDER_ORDER"), now=NOW), 10)

    def test_bad_data_retries_in_one_minute(self):
        self.assertEqual(next_delay_seconds(self.result("HOLD_BAD_MARKET_DATA"), now=NOW), 60)


    def test_operator_halt_is_rechecked_each_minute(self):
        self.assertEqual(next_delay_seconds(self.result("OPERATOR_HALTED"), now=NOW), 60)

    def test_reconciliation_waits(self):
        self.assertEqual(next_delay_seconds(self.result("BLOCKED_RECONCILIATION"), now=NOW), 300)

    def test_hold_waits_until_after_next_hour_close(self):
        delay = next_delay_seconds(self.result("HOLD"), now=NOW)
        self.assertEqual(delay, 1378.0)

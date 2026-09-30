import unittest
from decimal import Decimal

from signal_vault.kalshi_cloud_sidecar import CLOUD_PLANNED_MARKET_COUNT
from signal_vault.kalshi_prospective_shadow_gate import (
    MIN_CAPTURE_COVERAGE,
    MIN_VALID_PROSPECTIVE_MARKETS,
)


class KalshiForwardSampleBufferTests(unittest.TestCase):
    def test_cloud_plan_buffer_tolerates_two_market_failures_under_frozen_gate(self):
        self.assertEqual(CLOUD_PLANNED_MARKET_COUNT,22)
        valid_after_two_failures=CLOUD_PLANNED_MARKET_COUNT-2
        coverage=Decimal(valid_after_two_failures)/Decimal(
            CLOUD_PLANNED_MARKET_COUNT
        )
        self.assertGreaterEqual(
            valid_after_two_failures,
            MIN_VALID_PROSPECTIVE_MARKETS,
        )
        self.assertGreaterEqual(coverage,MIN_CAPTURE_COVERAGE)

    def test_three_full_market_failures_exceed_frozen_coverage_tolerance(self):
        valid_after_three_failures=CLOUD_PLANNED_MARKET_COUNT-3
        coverage=Decimal(valid_after_three_failures)/Decimal(
            CLOUD_PLANNED_MARKET_COUNT
        )
        self.assertLess(coverage,MIN_CAPTURE_COVERAGE)

    def test_buffer_does_not_change_frozen_minimum_valid_market_requirement(self):
        self.assertEqual(MIN_VALID_PROSPECTIVE_MARKETS,20)
        self.assertEqual(MIN_CAPTURE_COVERAGE,Decimal("0.90"))
        self.assertGreater(
            CLOUD_PLANNED_MARKET_COUNT,
            MIN_VALID_PROSPECTIVE_MARKETS,
        )


if __name__=="__main__":
    unittest.main()

import unittest

from signal_vault.market_capabilities import (
    market_capability,
    multimarket_capability_snapshot,
)


class MultiMarketCapabilityTests(unittest.TestCase):
    def test_three_market_lanes_exist_and_live_is_disabled(self):
        result = multimarket_capability_snapshot()
        self.assertEqual(set(result["markets"]), {"crypto", "us_equity", "kalshi"})
        self.assertTrue(result["all_live_money_disabled"])
        self.assertTrue(result["all_paper_order_submission_disabled"])
        for lane in result["markets"].values():
            self.assertFalse(lane["live_order_submission"])
            self.assertFalse(lane["live_money_available"])

    def test_equities_and_kalshi_are_separate_lanes(self):
        self.assertEqual(market_capability("us_equity")["provider"], "alpaca")
        self.assertEqual(market_capability("kalshi")["provider"], "kalshi")

    def test_unknown_market_fails_closed(self):
        with self.assertRaises(ValueError):
            market_capability("forex")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()

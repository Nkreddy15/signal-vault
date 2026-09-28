import unittest
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from signal_vault.risk import RiskEngine, RiskLimits
from signal_vault.domain import TradeIntent, PortfolioSnapshot, Side


NOW = datetime(2026, 9, 28, tzinfo=timezone.utc)


def order(**changes):
    return replace(TradeIntent(market="crypto", venue="alpaca", symbol="BTC/USD",
                               side=Side.BUY, notional_usd=Decimal("15"),
                               client_order_id="order1", signal_id="signal1",
                               quote_timestamp=NOW), **changes)


def account(**changes):
    return replace(PortfolioSnapshot(equity_usd=Decimal("100"), cash_usd=Decimal("100"),
                                     peak_equity_usd=Decimal("100"),
                                     session_start_equity_usd=Decimal("100")), **changes)


class RiskPolicyValidationTests(unittest.TestCase):
    def test_reject_nan_infinity_negative_non_decimal_limits(self):
        for bad in (Decimal("NaN"), Decimal("Infinity"), Decimal("-1"), Decimal("0"), "15"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                RiskLimits(max_single_buy_usd=bad)
        with self.assertRaises(ValueError):
            RiskLimits(max_total_long_exposure_usd=Decimal("NaN"))

    def test_single_limit_cannot_exceed_total_limit(self):
        with self.assertRaises(ValueError):
            RiskLimits(max_single_buy_usd=Decimal("50"),
                       max_total_long_exposure_usd=Decimal("30"))

    def test_invalid_quote_age_fails_in_constructor(self):
        for bad in (0, -1, 3601, False, True, "90"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                RiskLimits(max_quote_age_seconds=bad)

    def test_malformed_snapshot_rejected_not_crashed(self):
        engine = RiskEngine()
        self.assertFalse(engine.evaluate(order(), account(long_positions_usd=None), now=NOW).approved)
        self.assertFalse(engine.evaluate(order(), account(halted="false"), now=NOW).approved)
        self.assertFalse(engine.evaluate(order(), account(long_positions_usd={"OTHER": Decimal("2")},
                                                  equity_usd=Decimal("102")), now=NOW).approved)

    def test_inconsistent_marked_equity_rejected(self):
        engine = RiskEngine()
        proposal = order(notional_usd=Decimal("1"))
        actual = account(equity_usd=Decimal("90"), cash_usd=Decimal("80"),
                         long_positions_usd={"BTC/USD": Decimal("15")})
        result = engine.evaluate(proposal, actual, now=NOW)
        self.assertFalse(result.approved)
        self.assertIn("portfolio marked equity disagrees with cash plus held positions", result.reasons)

    def test_malformed_timestamp_and_ids_rejected_without_exception(self):
        engine = RiskEngine()
        self.assertFalse(engine.evaluate(order(quote_timestamp="not a timestamp"), account(), now=NOW).approved)
        self.assertFalse(engine.evaluate(order(client_order_id=None), account(), now=NOW).approved)
        self.assertFalse(engine.evaluate(order(signal_id=4), account(), now=NOW).approved)
        self.assertFalse(engine.evaluate(order(), account(), now="not datetime").approved)


if __name__ == "__main__":
    unittest.main()

import unittest
from decimal import Decimal

from signal_vault.venue_rules import CryptoVenueRules


def asset(**changes):
    value = {"symbol": "BTC/USD", "class": "crypto", "status": "active",
             "tradable": True, "fractionable": True,
             "min_order_size": "0.00015", "min_trade_increment": "0.00001",
             "price_increment": "1"}
    value.update(changes)
    return value


class VenueRulesTests(unittest.TestCase):
    def test_parse_provider_rules_and_dynamic_minimum(self):
        r = CryptoVenueRules.from_asset(asset())
        self.assertEqual(r.minimum_notional_at(Decimal("70000")), Decimal("10.50000"))
        r.validate_buy_notional(Decimal("15.00"), Decimal("70000"))

    def test_below_dynamic_minimum_rejected_without_upsize(self):
        r = CryptoVenueRules.from_asset(asset())
        with self.assertRaisesRegex(ValueError, "dynamic minimum"):
            r.validate_buy_notional(Decimal("10.00"), Decimal("70000"))

    def test_sell_must_respect_minimum_and_increment(self):
        r = CryptoVenueRules.from_asset(asset())
        r.validate_sell_qty(Decimal("0.00020"), Decimal("70000"))
        with self.assertRaises(ValueError):
            r.validate_sell_qty(Decimal("0.000195"), Decimal("70000"))
        with self.assertRaises(ValueError):
            r.validate_sell_qty(Decimal("0.00010"), Decimal("70000"))

    def test_missing_or_malformed_constraints_fail_closed(self):
        for key in ("min_order_size", "min_trade_increment", "price_increment"):
            bad = asset(); bad.pop(key)
            with self.subTest(key=key), self.assertRaises(ValueError):
                CryptoVenueRules.from_asset(bad)
        with self.assertRaises(ValueError):
            CryptoVenueRules.from_asset(asset(min_order_size="NaN"))

import unittest
from decimal import Decimal
from signal_vault.venue_rules import BtcVenueRules

ASSET={"symbol":"BTC/USD", "class":"crypto", "status":"active",
       "tradable":True,"fractionable":True,"min_order_size":"0.0001",
       "min_trade_increment":"0.0001","price_increment":"1"}

class VenueRulesTests(unittest.TestCase):
    def test_no_auto_upsize_for_100_dollar_pilot(self):
        rules=BtcVenueRules.from_asset(ASSET)
        rules.check_buy(notional_usd=Decimal('15'),reference_price=Decimal('100000'))
        with self.assertRaises(PermissionError):
            rules.check_buy(notional_usd=Decimal('15'),reference_price=Decimal('200000'))
        with self.assertRaises(ValueError):
            rules.check_buy(notional_usd=Decimal('15.001'),reference_price=Decimal('100000'))
    def test_fee_reduced_position_must_not_be_labeled_full_exit(self):
        rules=BtcVenueRules.from_asset(ASSET)
        preview=rules.preview_sell(held_base_qty=Decimal('0.000229425'),
                                   reference_price=Decimal('65000'))
        self.assertTrue(preview.can_prepare_dust_aware_intent)
        self.assertEqual(preview.executable_base_qty,Decimal('0.0002'))
        self.assertEqual(preview.residual_dust_qty,Decimal('0.000029425'))
        self.assertEqual(preview.estimated_sell_usd,Decimal('13.0000'))
        self.assertIn('PREVIEW ONLY',preview.note)
    def test_dust_only_does_not_generate_an_unexecutable_order(self):
        rules=BtcVenueRules.from_asset(ASSET)
        x=rules.preview_sell(held_base_qty=Decimal('0.00009'),
                             reference_price=Decimal('65000'))
        self.assertFalse(x.can_prepare_dust_aware_intent)
        self.assertEqual(x.executable_base_qty,Decimal('0'))
        self.assertEqual(x.residual_dust_qty,Decimal('0.00009'))
    def test_stale_or_bad_metadata_rejected(self):
        for change in ({'min_order_size':'NaN'},{'min_trade_increment':'0'},
                       {'price_increment':'Infinity'},{'symbol':'ETH/USD'},
                       {'status':'inactive'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                BtcVenueRules.from_asset({**ASSET,**change})

if __name__=='__main__':unittest.main()

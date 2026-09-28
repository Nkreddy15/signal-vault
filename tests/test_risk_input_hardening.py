"""Untrusted agent inputs should be rejected, not crash the trading loop."""
import unittest
from dataclasses import replace
from datetime import datetime,timezone
from decimal import Decimal
from signal_vault.risk import RiskEngine,RiskLimits
from signal_vault.domain import PortfolioSnapshot,TradeIntent,Side

T=datetime(2026,9,28,23,0,tzinfo=timezone.utc)
P=PortfolioSnapshot(Decimal('100'),Decimal('100'),Decimal('100'),Decimal('100'))
I=TradeIntent('crypto','alpaca','BTC/USD',Side.BUY,Decimal('15'),'agent-intent-1','hash',T)

class InputHardeningTests(unittest.TestCase):
    def test_reject_wrong_timestamp_or_identity_fields_without_exception(self):
        engine=RiskEngine()
        for change in ({'quote_timestamp':None},{'quote_timestamp':'2026-09-28'},
                       {'client_order_id':None},{'signal_id':None}):
            with self.subTest(change=change):
                decision=engine.evaluate(replace(I,**change),P,now=T)
                self.assertFalse(decision.approved)

    def test_unrecognized_position_data_rejected(self):
        engine=RiskEngine()
        for bad in (None,{'ETH/USD':Decimal('2')},{'BTC/USD':Decimal('NaN')}):
            with self.subTest(bad=bad):
                self.assertFalse(engine.evaluate(I,replace(P,long_positions_usd=bad),now=T).approved)

    def test_invalid_limits_cannot_be_constructed(self):
        for kw in ({'max_single_buy_usd':Decimal('NaN')},
                   {'max_total_long_exposure_usd':Decimal('-1')},
                   {'max_quote_age_seconds':True},
                   {'allowed_venue':'unknown'}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                RiskLimits(**kw)

if __name__=='__main__':unittest.main()

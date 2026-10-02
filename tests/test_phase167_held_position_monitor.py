import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.experimental_paper_position_monitor import inspect_held_position
from signal_vault.paper_credentials import PaperCredentials

UTC=timezone.utc


class Bar:
    def __init__(self,start,close):
        self.symbol="BTC/USD"
        self.start=start
        self.open=close
        self.high=close+Decimal("1")
        self.low=close-Decimal("1")
        self.close=close
        self.volume=Decimal("1")
        self.source="fixture"


class BarsFactory:
    prices=[]
    def __init__(self,*args,**kwargs): pass
    def fetch(self,*,start,end,as_of):
        return tuple(Bar(start+timedelta(hours=i),p) for i,p in enumerate(self.prices))


class Reader:
    def __init__(self,*args,**kwargs): pass
    def get_account(self):
        return {"status":"ACTIVE","trading_blocked":False}
    def get_positions(self):
        return ({
            "symbol":"BTCUSD","side":"long","qty":"0.000117",
            "market_value":"10.10","avg_entry_price":"85470.08",
            "current_price":"86324.00",
        },)
    def get_open_orders(self): return ()


class Phase167HeldPositionMonitorTests(unittest.TestCase):
    def test_momentum_sell_at_minus_50_bps_or_worse(self):
        prices=[Decimal("100")]*72
        prices[47]=Decimal("100")
        prices[71]=Decimal("99")
        BarsFactory.prices=prices
        out=inspect_held_position(
            strategy_name="generic-momentum24bar50bps-v1-predeclared",
            credentials=PaperCredentials("paper-key","paper-secret"),
            now=datetime(2026,10,2,18,5,tzinfo=UTC),
            reader_factory=Reader,
            bars_factory=BarsFactory,
        )
        self.assertEqual(out["held_state_action"],"sell")
        self.assertEqual(out["strategy_metrics"]["sell_threshold_bps"],"-50")
        self.assertEqual(out["strategy_metrics"]["current_24h_return_bps"],"-100.00")
        self.assertEqual(out["next_action"],"REVIEW_SUPERVISED_PAPER_SELL")
        self.assertFalse(out["action_is_order_authority"])

    def test_momentum_hold_above_exit_threshold(self):
        prices=[Decimal("100")]*72
        prices[47]=Decimal("100")
        prices[71]=Decimal("100.2")
        BarsFactory.prices=prices
        out=inspect_held_position(
            strategy_name="generic-momentum24bar50bps-v1-predeclared",
            credentials=PaperCredentials("paper-key","paper-secret"),
            now=datetime(2026,10,2,18,5,tzinfo=UTC),
            reader_factory=Reader,
            bars_factory=BarsFactory,
        )
        self.assertEqual(out["held_state_action"],"hold")
        self.assertEqual(out["strategy_metrics"]["current_24h_return_bps"],"20.000")
        self.assertEqual(out["next_action"],"CONTINUE_HOURLY_HELD_POSITION_OBSERVATION")
        self.assertEqual(out["order_submission"],"DISABLED")


if __name__=="__main__":
    unittest.main()

from datetime import datetime,timedelta,timezone
from decimal import Decimal
import unittest

from signal_vault.cross_sectional_crypto_research import (
    CrossSectionalConfig,
    SYMBOLS,
    simulate_cross_sectional_strength,
)
from signal_vault.research_universe import ResearchBar

START=datetime(2026,1,1,tzinfo=timezone.utc)
HOUR=timedelta(hours=1)


def dataset(growth):
    out={}
    for k,sym in enumerate(SYMBOLS):
        rows=[]
        price=Decimal("100")+Decimal(k)
        for i in range(240):
            p=price*(Decimal("1")+growth.get(sym,Decimal("0"))*Decimal(i))
            rows.append(ResearchBar(
                sym,START+i*HOUR,p,p+1,p-1,p,Decimal("100"),
                "alpaca_crypto_us",START+(i+1)*HOUR,False,
            ))
        out[sym]=tuple(rows)
    return out


class CrossSectionalStrengthTests(unittest.TestCase):
    def test_flat_market_stays_cash(self):
        result=simulate_cross_sectional_strength(
            dataset({}),
            config=CrossSectionalConfig(min_strength_bps=Decimal("150")),
            evaluation_start_index=100,
            evaluation_end_index=220,
        )
        self.assertEqual(result["fill_count"],0)
        self.assertEqual(result["open_positions"],[])
        self.assertEqual(result["net_marked_pnl_usd"],"0")

    def test_strongest_assets_are_bounded_to_two_positions(self):
        growth={
            "BTC/USD":Decimal("0.002"),
            "ETH/USD":Decimal("0.0018"),
            "SOL/USD":Decimal("0.0016"),
        }
        result=simulate_cross_sectional_strength(
            dataset(growth),
            config=CrossSectionalConfig(min_strength_bps=Decimal("50")),
            evaluation_start_index=100,
            evaluation_end_index=220,
        )
        self.assertLessEqual(len(result["open_positions"]),2)
        self.assertGreater(result["fill_count"],0)
        self.assertEqual(result["broker_order_submission"],"DISABLED")
        self.assertEqual(result["live_trading"],"UNAVAILABLE")

    def test_misaligned_history_fails_closed(self):
        data=dataset({})
        bad=list(data["BTC/USD"])
        bad[120]=ResearchBar(
            "BTC/USD",bad[120].start_utc+timedelta(minutes=1),
            bad[120].open,bad[120].high,bad[120].low,bad[120].close,
            bad[120].volume,bad[120].feed,bad[120].captured_utc,False,
        )
        data["BTC/USD"]=tuple(bad)
        with self.assertRaises(ValueError):
            simulate_cross_sectional_strength(
                data,evaluation_start_index=100,evaluation_end_index=220)


if __name__=="__main__":
    unittest.main()

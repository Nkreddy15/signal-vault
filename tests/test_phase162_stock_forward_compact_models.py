from __future__ import annotations

import unittest
from datetime import datetime,timedelta,timezone
from decimal import Decimal

from signal_vault.ci_historical_equities import SYMBOLS
from signal_vault.research_universe import ResearchBar
from signal_vault.stock_forward_compact_models import (
    FEATURE_NAMES,FROZEN_STOCK_MODELS,
    MINIMUM_COMPLETED_CORE_HOURS,
    latest_stock_feature_vectors,
)

START=datetime(2026,1,2,15,tzinfo=timezone.utc)

def sample(count:int):
    rows={}
    for offset,symbol in enumerate(SYMBOLS):
        values=[]
        for index in range(count):
            close=Decimal("100")+Decimal(offset*20)+Decimal(index)/Decimal("5")+Decimal((index%9)-4)/Decimal("100")
            opened=START+timedelta(hours=index)
            values.append(ResearchBar(
                symbol=symbol,
                start_utc=opened,
                open=close-Decimal("0.02"),
                high=close+Decimal("0.08"),
                low=close-Decimal("0.07"),
                close=close,
                volume=Decimal("100000")+Decimal((index+offset)%23)*Decimal("100"),
                feed="alpaca_equity_iex|adjustment=all",
                captured_utc=opened+timedelta(hours=1,minutes=7),
                prospective=True,
            ))
        rows[symbol]=tuple(values)
    return rows

class StockCompactModelTests(unittest.TestCase):
    def test_requires_49_verified_hours(self):
        with self.assertRaises(ValueError):
            latest_stock_feature_vectors(
                sample(MINIMUM_COMPLETED_CORE_HOURS-1)
            )

    def test_latest_feature_contract_matches_two_models(self):
        vectors,_=latest_stock_feature_vectors(sample(60))
        self.assertEqual(set(vectors),set(SYMBOLS))
        self.assertTrue(
            all(len(vector)==len(FEATURE_NAMES) for vector in vectors.values())
        )
        self.assertEqual(
            {model.name for model in FROZEN_STOCK_MODELS},
            {"ridge10","robust_irls_v1"},
        )

    def test_forward_rows_must_be_prospective_verified_iex(self):
        rows=sample(60)
        bad=dict(rows)
        source=list(bad["AAPL"])
        item=source[-1]
        source[-1]=ResearchBar(
            symbol=item.symbol,start_utc=item.start_utc,
            open=item.open,high=item.high,low=item.low,close=item.close,
            volume=item.volume,feed=item.feed,captured_utc=item.captured_utc,
            prospective=False,
        )
        bad["AAPL"]=tuple(source)
        with self.assertRaises(ValueError):
            latest_stock_feature_vectors(bad)

if __name__=="__main__":
    unittest.main()

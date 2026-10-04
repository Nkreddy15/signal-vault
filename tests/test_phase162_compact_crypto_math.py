from __future__ import annotations

import unittest
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from statistics import stdev

from signal_vault.crypto_forward_compact_models import (
    FEATURE_NAMES,FROZEN_MODELS,MINIMUM_COMPLETED_BARS,
    _SHARED_MEAN,latest_feature_vectors,
)
from signal_vault.research_universe import ResearchBar

START=datetime(2026,1,1,tzinfo=timezone.utc)

def data(count:int):
    result={}
    for offset,symbol in enumerate(("BTC/USD","ETH/USD","SOL/USD")):
        rows=[]
        for index in range(count):
            close=Decimal("100")+Decimal(offset*10)+Decimal(index)/Decimal("10")+Decimal((index%7)-3)/Decimal("100")
            rows.append(ResearchBar(
                symbol=symbol,
                start_utc=START+timedelta(hours=index),
                open=close-Decimal("0.02"),
                high=close+Decimal("0.05"),
                low=close-Decimal("0.05"),
                close=close,
                volume=Decimal("1000")+Decimal((index+offset)%17),
                feed="alpaca_crypto_us",
                captured_utc=START+timedelta(hours=count+2),
                prospective=False,
            ))
        result[symbol]=tuple(rows)
    return result

class CompactCryptoMathTests(unittest.TestCase):
    def test_requires_73_bars(self):
        with self.assertRaises(ValueError):
            latest_feature_vectors(data(MINIMUM_COMPLETED_BARS-1))

    def test_vol72_matches_72_return_sample_std(self):
        source=data(MINIMUM_COMPLETED_BARS)
        vectors,_=latest_feature_vectors(source)
        closes=[float(row.close) for row in source["BTC/USD"]]
        expected=stdev([
            closes[i]/closes[i-1]-1.0
            for i in range(1,len(closes))
        ])
        actual=vectors["BTC/USD"][FEATURE_NAMES.index("vol_72h")]
        self.assertAlmostEqual(actual,expected,places=15)

    def test_model_scaler_mean_maps_to_intercept(self):
        for model in FROZEN_MODELS:
            self.assertAlmostEqual(
                model.predict(_SHARED_MEAN),model.intercept,places=15
            )

if __name__=="__main__":
    unittest.main()

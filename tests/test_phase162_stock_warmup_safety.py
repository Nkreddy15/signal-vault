from __future__ import annotations

import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.ci_historical_equities import SYMBOLS
from signal_vault.equity_model_warmup import (
    MODEL_WARMUP_CHILD,
    load_stock_model_warmup,
)
from signal_vault.research_universe import ResearchBar
from signal_vault.stock_forward_compact_models import (
    latest_stock_feature_vectors,
)

START=datetime(2026,1,2,15,tzinfo=timezone.utc)

def mixed_rows():
    result={}
    for offset,symbol in enumerate(SYMBOLS):
        rows=[]
        for index in range(60):
            close=Decimal("100")+Decimal(offset*10)+Decimal(index)/Decimal("10")
            opened=START+timedelta(hours=index)
            rows.append(ResearchBar(
                symbol=symbol,
                start_utc=opened,
                open=close-Decimal("0.01"),
                high=close+Decimal("0.05"),
                low=close-Decimal("0.05"),
                close=close,
                volume=Decimal("1000")+Decimal(index%11),
                feed="alpaca_equity_iex|adjustment=all",
                captured_utc=opened+timedelta(hours=1,minutes=7),
                prospective=index>=48,
            ))
        result[symbol]=tuple(rows)
    return result

class StockWarmupSafetyTests(unittest.TestCase):
    def test_read_only_loader_does_not_create_missing_namespace(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            root.chmod(0o700)
            with self.assertRaises(ValueError):
                load_stock_model_warmup(
                    stock_root=root,
                    first_forward_open=START,
                )
            self.assertFalse((root/MODEL_WARMUP_CHILD).exists())

    def test_historical_prefix_can_feed_features_only_when_explicit(self):
        rows=mixed_rows()
        with self.assertRaises(ValueError):
            latest_stock_feature_vectors(rows)
        vectors,_=latest_stock_feature_vectors(
            rows,
            allow_historical_warmup=True,
        )
        self.assertEqual(set(vectors),set(SYMBOLS))

    def test_historical_rows_after_prospective_rows_are_rejected(self):
        rows=mixed_rows()
        bad=dict(rows)
        items=list(bad["AAPL"])
        last=items[-1]
        items[-1]=ResearchBar(
            symbol=last.symbol,start_utc=last.start_utc,
            open=last.open,high=last.high,low=last.low,close=last.close,
            volume=last.volume,feed=last.feed,
            captured_utc=last.captured_utc,prospective=False,
        )
        bad["AAPL"]=tuple(items)
        with self.assertRaises(ValueError):
            latest_stock_feature_vectors(
                bad,
                allow_historical_warmup=True,
            )

if __name__=="__main__":
    unittest.main()

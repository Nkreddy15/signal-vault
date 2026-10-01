from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest

from signal_vault.multi_asset_simulation import (
    HypothesisKind,
    ResearchHypothesis,
    precompute_closed_bar_decisions,
)
from signal_vault.research_universe import ResearchBar
from signal_vault.strategy import Action


HOUR=timedelta(hours=1)
START=datetime(2026,1,1,tzinfo=timezone.utc)


def bars(prices):
    out=[]
    for i,p in enumerate(prices):
        price=Decimal(str(p))
        out.append(ResearchBar(
            "BTC/USD",
            START+i*HOUR,
            price,
            price+Decimal("1"),
            price-Decimal("1"),
            price,
            Decimal("100"),
            "alpaca_crypto_us",
            START+(i+1)*HOUR,
            False,
        ))
    return tuple(out)


class Phase142RegimeHypothesisTests(unittest.TestCase):
    def config(self, **kw):
        base=dict(
            kind=HypothesisKind.EMA_REGIME,
            name="test-regime",
            fast_bars=3,
            slow_bars=5,
            volatility_lookback_bars=3,
            min_ema_spread_bps=Decimal("20"),
            min_avg_abs_return_bps=Decimal("10"),
        )
        base.update(kw)
        return ResearchHypothesis(**base)

    def test_quiet_market_does_not_buy(self):
        seq=bars(["100","100.01","100.02","100.03","100.04","100.05","100.06","100.07","100.08"])
        decisions=precompute_closed_bar_decisions(seq,config=self.config())
        self.assertTrue(all(
            pair is None or pair[0].action is not Action.BUY
            for pair in decisions
        ))

    def test_strong_trend_with_volatility_can_buy(self):
        seq=bars(["100","101","103","106","110","115","121","128","136","145","155"])
        decisions=precompute_closed_bar_decisions(seq,config=self.config())
        self.assertTrue(any(
            pair is not None and pair[0].action is Action.BUY
            for pair in decisions
        ))

    def test_bearish_crossover_exits_immediately_when_held(self):
        seq=bars(["100","103","107","112","118","124","120","114","108","102","96"])
        decisions=precompute_closed_bar_decisions(seq,config=self.config())
        self.assertTrue(any(
            pair is not None and pair[1].action is Action.SELL
            for pair in decisions
        ))


if __name__=="__main__":
    unittest.main()

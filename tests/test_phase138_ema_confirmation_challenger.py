import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.multi_asset_simulation import (
    HypothesisKind,
    ResearchHypothesis,
    decide_on_prior_closes,
)
from signal_vault.research_universe import ResearchBar
from signal_vault.strategy import Action


UTC=timezone.utc


def bars(values):
    out=[]
    start=datetime(2026,9,1,tzinfo=UTC)
    for i,value in enumerate(values):
        opened=start+timedelta(hours=i)
        out.append(ResearchBar(
            symbol="BTC/USD",
            feed="test",
            start_utc=opened,
            closed_utc=opened+timedelta(hours=1),
            open=Decimal(str(value)),
            high=Decimal(str(value)),
            low=Decimal(str(value)),
            close=Decimal(str(value)),
            volume=Decimal("1"),
        ))
    return tuple(out)


class Phase138EmaConfirmationTests(unittest.TestCase):
    def test_confirmation_hypothesis_requires_extra_closed_bar(self):
        cfg=ResearchHypothesis(
            HypothesisKind.EMA_CONFIRM,
            "generic-ema12x26-confirm2-v2-predeclared",
        )
        self.assertEqual(cfg.warmup_bars,29)

    def test_confirmation_entry_is_never_earlier_than_plain_ema_entry(self):
        plain=ResearchHypothesis(
            HypothesisKind.EMA,
            "generic-ema12x26-v1-predeclared",
        )
        confirm=ResearchHypothesis(
            HypothesisKind.EMA_CONFIRM,
            "generic-ema12x26-confirm2-v2-predeclared",
        )
        # Long flat regime followed by a persistent rise gives a bullish cross.
        seq=bars([100]*28+[101,102,103,104,105])
        plain_buy=None
        confirm_buy=None
        for i in range(29,len(seq)+1):
            next_open=seq[i-1].closed_utc
            p=decide_on_prior_closes(
                seq[:i],config=plain,has_position=False,next_open_utc=next_open
            )
            q=decide_on_prior_closes(
                seq[:i],config=confirm,has_position=False,next_open_utc=next_open
            )
            if p.action is Action.BUY and plain_buy is None:
                plain_buy=i
            if q.action is Action.BUY and confirm_buy is None:
                confirm_buy=i
        self.assertIsNotNone(plain_buy)
        self.assertIsNotNone(confirm_buy)
        self.assertGreater(confirm_buy,plain_buy)

    def test_bearish_exit_remains_immediate_cross(self):
        cfg=ResearchHypothesis(
            HypothesisKind.EMA_CONFIRM,
            "generic-ema12x26-confirm2-v2-predeclared",
        )
        seq=bars([100]*28+[104,105,106,107,95,90])
        seen=False
        for i in range(29,len(seq)+1):
            decision=decide_on_prior_closes(
                seq[:i],config=cfg,has_position=True,
                next_open_utc=seq[i-1].closed_utc,
            )
            if decision.action is Action.SELL:
                seen=True
                break
        self.assertTrue(seen)


if __name__=="__main__":
    unittest.main()

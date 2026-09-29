"""Exact legacy/linear synthetic decision parity across two book states.

The cached algorithm must not change one next-open action OR evidence hash:
the point of Phase 7 is faster 6-asset historical research, not a hidden
strategy/version selection, changed fill rule or new broker authorization.
"""
from __future__ import annotations

import random
import unittest
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from decimal import Decimal

from signal_vault.multi_asset_simulation import (
    HYPOTHESES,HypothesisKind,ResearchHypothesis,
    decide_on_prior_closes,precompute_closed_bar_decisions,
    ExplicitRoundTripCosts,simulate_one_asset,
)
from signal_vault.research_universe import ResearchBar,candidate

START=datetime(2026,9,1,0,tzinfo=timezone.utc)
HOUR=timedelta(hours=1)
COST=ExplicitRoundTripCosts(Decimal("25"),Decimal("4"),Decimal("10"))


def history(*,symbol="BTC/USD",count=96,seed=9842,times=None):
    rng=random.Random(seed)
    dates=tuple(times) if times is not None else tuple(START+i*HOUR for i in range(count))
    px=Decimal("100")
    bars=[]
    now=dates[-1]+HOUR+timedelta(minutes=8)
    for t in dates:
        px=max(Decimal("6"),px+Decimal(rng.choice((-8,-5,-3,-1,0,1,3,5,8))))
        bars.append(ResearchBar(
            symbol,t,px,px+Decimal("2"),px-Decimal("2"),px,
            Decimal("10"),"synthetic_provider_fixture",now,False))
    return tuple(bars)


class CachedClosedBarSignalParityTests(unittest.TestCase):
    def test_all_four_fixed_hypotheses_match_legacy_at_every_index_and_position_state(self):
        for symbol in ("BTC/USD","ETH/USD","SOL/USD","LTC/USD","LINK/USD","AVAX/USD"):
            rows=history(symbol=symbol,count=90)
            for h in HYPOTHESES:
                cached=precompute_closed_bar_decisions(rows,config=h)
                self.assertEqual(len(cached),len(rows))
                self.assertIsNone(cached[0])
                for idx in range(1,len(rows)):
                    for held in (False,True):
                        old=decide_on_prior_closes(
                            rows[:idx],config=h,has_position=held,
                            next_open_utc=rows[idx].start_utc)
                        self.assertEqual(
                            cached[idx][1 if held else 0],old,
                            (symbol,h.name,idx,held))

    def test_multiple_custom_ema_and_momentum_parameters_do_not_shift_crosses(self):
        rows=history(count=115,seed=1425)
        options=(
            ResearchHypothesis(HypothesisKind.EMA,"ema3x7-parity",fast_bars=3,slow_bars=7),
            ResearchHypothesis(HypothesisKind.EMA,"ema7x23-parity",fast_bars=7,slow_bars=23),
            ResearchHypothesis(HypothesisKind.MOMENTUM,"mom4-parity",lookback_bars=4,
                               entry_return_bps=Decimal("0"),
                               exit_return_bps=Decimal("-25")),
            ResearchHypothesis(HypothesisKind.MOMENTUM,"mom19-parity",lookback_bars=19,
                               entry_return_bps=Decimal("200"),
                               exit_return_bps=Decimal("-100")),
        )
        for h in options:
            cached=precompute_closed_bar_decisions(rows,config=h)
            for idx in range(1,len(rows)):
                for held in (False,True):
                    self.assertEqual(
                        cached[idx][int(held)],
                        decide_on_prior_closes(
                            rows[:idx],config=h,has_position=held,
                            next_open_utc=rows[idx].start_utc))

    def test_equity_session_gap_is_not_interpreted_as_continuous_crypto(self):
        times=tuple(
            datetime(2026,9,1,13,30,tzinfo=timezone.utc) +
            timedelta(days=day,hours=i)
            for day in range(9) for i in range(6))
        rows=history(symbol="SPY",times=times)
        for h in HYPOTHESES:
            cache=precompute_closed_bar_decisions(rows,config=h)
            for idx in range(1,len(rows)):
                for held in (False,True):
                    self.assertEqual(
                        cache[idx][int(held)],
                        decide_on_prior_closes(
                            rows[:idx],config=h,has_position=held,
                            next_open_utc=rows[idx].start_utc))
        result=simulate_one_asset(
            rows,spec=candidate("SPY"),
            as_of=rows[-1].closed_utc+timedelta(minutes=8),
            hypothesis=HYPOTHESES[2],costs=COST,
            expected_equity_session_opens_utc=times)
        self.assertEqual(result["decision_evaluation_algorithm"],
                         "v2_linear_precomputed_closed_bar_state_equivalent")
        self.assertEqual(result["broker_order_submission"],"DISABLED")

    def test_mixed_symbols_feeds_missing_timezone_and_overlapping_hour_rejected(self):
        rows=history(count=70)
        bad=(
            (rows[0],replace(rows[1],symbol="ETH/USD"),*rows[2:]),
            (rows[0],replace(rows[1],feed="different_feed"),*rows[2:]),
            (rows[0],replace(rows[1],start_utc=rows[0].start_utc),*rows[2:]),
            (replace(rows[0],start_utc=rows[0].start_utc.replace(tzinfo=None)),*rows[1:]),
        )
        for data in bad:
            with self.subTest(data=data[:2]),self.assertRaises(ValueError):
                precompute_closed_bar_decisions(data,config=HYPOTHESES[2])

    def test_large_sample_cash_passive_ema_momentum_results_do_not_submit_trades(self):
        rows=history(count=420)
        for h in HYPOTHESES:
            result=simulate_one_asset(
                rows,spec=candidate("BTC/USD"),
                as_of=rows[-1].closed_utc+timedelta(minutes=8),
                hypothesis=h,costs=COST)
            self.assertEqual(result["decision_evaluation_algorithm"],
                             "v2_linear_precomputed_closed_bar_state_equivalent")
            self.assertEqual(result["broker_order_submission"],"DISABLED")
            self.assertEqual(result["live_trading"],"UNAVAILABLE")


if __name__=="__main__":
    unittest.main()

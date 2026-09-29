"""Deterministic synthetic multi-market, cost-aware next-open research tests.

No imported order APIs, provider calls, actual fills, or Railway cloud volume.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.multi_asset_simulation import (
    ExplicitRoundTripCosts, HYPOTHESES, HypothesisKind, ResearchHypothesis,
    chronological_three_way_review, decide_on_prior_closes, simulate_one_asset,
)
from signal_vault.research_universe import ResearchBar, candidate
from signal_vault.strategy import Action

UTC=timezone.utc
HOUR=timedelta(hours=1)
FIRST=datetime(2026,9,20,0,0,tzinfo=UTC)
COST=ExplicitRoundTripCosts(
    taker_fee_bps=Decimal("25"),
    full_spread_bps=Decimal("4"),
    slippage_per_side_bps=Decimal("10"),
)


def sample(symbol="BTC/USD", *, count=70, prices=None,
           times=None, feed="synthetic_closed_hourly"):
    if times is None:
        times=tuple(FIRST + i*HOUR for i in range(count))
    else:
        count=len(times)
    if prices is None:
        prices=[Decimal("100")]*count
    captured=max(t + HOUR for t in times) + timedelta(minutes=8)
    return tuple(
        ResearchBar(
            symbol, date,
            Decimal(str(prices[i])), Decimal(str(prices[i]))+Decimal("2"),
            Decimal(str(prices[i]))-Decimal("2"),
            Decimal(str(prices[i])),Decimal("10"),feed,captured,False,
        )
        for i,date in enumerate(times)
    )


class MultiAssetSimulationTests(unittest.TestCase):
    def test_hypothesis_registry_is_predeclared_and_costs_are_explicit(self):
        self.assertEqual(
            {h.kind for h in HYPOTHESES},
            {HypothesisKind.CASH,HypothesisKind.PASSIVE,
             HypothesisKind.EMA,HypothesisKind.MOMENTUM})
        with self.assertRaises(ValueError):
            ExplicitRoundTripCosts(Decimal("-1"),Decimal("4"),Decimal("10"))
        with self.assertRaises(ValueError):
            ResearchHypothesis(HypothesisKind.EMA,"bad",fast_bars=50,slow_bars=20)

    def test_cash_and_passive_on_flat_market_with_friction(self):
        bars=sample()
        as_of=bars[-1].closed_utc+timedelta(minutes=8)
        cash=simulate_one_asset(
            bars,spec=candidate("BTC/USD"),as_of=as_of,
            hypothesis=HYPOTHESES[0],costs=COST)
        self.assertEqual(cash["final_marked_equity_usd"],"100")
        self.assertEqual(cash["fills"],[])
        passive=simulate_one_asset(
            bars,spec=candidate("BTC/USD"),as_of=as_of,
            hypothesis=HYPOTHESES[1],costs=COST)
        self.assertEqual(len(passive["fills"]),1)
        self.assertEqual(passive["fills"][0]["side"],"buy")
        self.assertLess(Decimal(passive["final_marked_equity_usd"]),Decimal("100"))
        self.assertEqual(
            Decimal(passive["final_marked_equity_usd"]),
            Decimal(passive["passive_same_allocation_final_marked_usd"]))
        self.assertTrue(passive["mark_is_not_liquidated"])
        self.assertLess(Decimal(passive["estimated_liquidation_equity_usd"]),
                        Decimal(passive["final_marked_equity_usd"]))
        self.assertTrue(passive["estimated_liquidation_not_an_order"])
        self.assertEqual(passive["broker_order_submission"],"DISABLED")
        self.assertFalse(passive["shared_portfolio_risk_evaluated"])

    def test_fills_use_next_open_only_and_never_future_close_for_decision(self):
        bars=sample(count=70,prices=[100+i*2 for i in range(70)])
        h=ResearchHypothesis(
            HypothesisKind.MOMENTUM,"synthetic-momentum-v1",
            lookback_bars=5,entry_return_bps=Decimal("50"),
            exit_return_bps=Decimal("-50"))
        first=max(h.warmup_bars,2)
        d=decide_on_prior_closes(
            bars[:first],config=h,has_position=False,
            next_open_utc=bars[first].start_utc)
        self.assertEqual(d.action,Action.BUY)
        with self.assertRaises(ValueError):
            decide_on_prior_closes(
                bars[:first+1],config=h,has_position=False,
                next_open_utc=bars[first].start_utc)
        one=simulate_one_asset(
            bars,spec=candidate("BTC/USD"),
            as_of=bars[-1].closed_utc+timedelta(minutes=8),
            hypothesis=h,costs=COST)
        fill=one["fills"][0]
        self.assertEqual(fill["at_open_utc"],bars[first].start_utc.isoformat())
        self.assertEqual(fill["decision_evidence_sha256"],d.evidence_sha256)
        # Change candle's FUTURE close while leaving its open fixed:
        # first decision/fill cannot be altered by that information.
        altered=list(bars)
        altered[first]=replace(
            altered[first],close=Decimal("999"),high=Decimal("1000"))
        altered=tuple(altered)
        second=simulate_one_asset(
            altered,spec=candidate("BTC/USD"),
            as_of=bars[-1].closed_utc+timedelta(minutes=8),
            hypothesis=h,costs=COST)
        self.assertEqual(second["fills"][0],fill)

    def test_ema_baseline_works_with_eth_without_btc_hardcode(self):
        values=[Decimal("130")-Decimal(i) for i in range(32)]
        values += [Decimal("98")+Decimal(4*(i+1)) for i in range(38)]
        rows=sample(symbol="ETH/USD",count=70,prices=values)
        config=ResearchHypothesis(
            HypothesisKind.EMA,"eth-generic-ema3x7-fixture",
            fast_bars=3,slow_bars=7)
        output=simulate_one_asset(
            rows,spec=candidate("ETH/USD"),
            as_of=rows[-1].closed_utc+timedelta(minutes=8),
            hypothesis=config,costs=COST)
        self.assertEqual(output["symbol"],"ETH/USD")
        self.assertIn(output["signal_counts"]["buy"],range(0,70))
        self.assertTrue(any(f["side"]=="buy" for f in output["fills"]))
        self.assertEqual(output["live_trading"],"UNAVAILABLE")

    def test_equities_require_separate_explicit_calendar_and_costs(self):
        # Shape-only synthetic calendar: 7 calendar blocks of 6 hourly
        # open timestamps separated overnight. No assertion of a real holiday.
        opens=tuple(
            datetime(2026,9,1,13,30,tzinfo=UTC)+timedelta(days=day,hours=i)
            for day in range(8) for i in range(6))
        rows=sample("SPY",times=opens,feed="synthetic_iex_adjusted")
        with self.assertRaises(ValueError):
            simulate_one_asset(
                rows,spec=candidate("SPY"),as_of=opens[-1]+HOUR,
                hypothesis=HYPOTHESES[0],costs=COST)
        equity_cost=ExplicitRoundTripCosts(
            Decimal("0"),Decimal("2"),Decimal("5"))
        report=simulate_one_asset(
            rows,spec=candidate("SPY"),
            as_of=opens[-1]+HOUR+timedelta(minutes=8),
            hypothesis=HYPOTHESES[1],costs=equity_cost,
            expected_equity_session_opens_utc=opens)
        self.assertEqual(report["market"],"us_equity")
        self.assertEqual(report["feed"],"synthetic_iex_adjusted")
        self.assertEqual(report["estimated_costs_not_measured_fills"]["taker_fee_bps_each_side"],"0")

    def test_daily_loss_cap_gates_new_buys_after_marked_drop(self):
        prices=[Decimal("100")]*35 + [Decimal("40")]*35
        rows=sample(prices=prices)
        result=simulate_one_asset(
            rows,spec=candidate("BTC/USD"),as_of=rows[-1].closed_utc,
            hypothesis=HYPOTHESES[1],costs=COST)
        # Passive keeps the open marked position; this is research only,
        # NOT a rule to automatically submit a liquidation order.
        self.assertEqual(len(result["fills"]),1)
        self.assertEqual(result["research_risk_gate_semantics_version"],
                         "v2_utc_daily_reset_plus_persistent_peak_drawdown_halt")
        self.assertIn((FIRST+timedelta(hours=35)).date().isoformat(),
                      result["utc_daily_entry_pause_dates"])
        # The $3 daily loss suspends new entries for the remainder of that
        # UTC day, but by the final next day the <$10 peak-loss guard has not
        # been breached: daily entry gate is permitted to reset.
        self.assertFalse(result["utc_daily_entry_pause_current"])
        self.assertFalse(result["persistent_peak_drawdown_entry_halt"])
        self.assertFalse(result["entry_blocked_by_loss_cap"])
        self.assertGreater(Decimal(result["max_marked_drawdown_usd"]),Decimal("3"))
        self.assertEqual(result["broker_order_submission"],"DISABLED")

    def test_three_way_review_has_no_evaluation_bar_overlap(self):
        rows=sample(count=116)
        result=chronological_three_way_review(
            rows,spec=candidate("BTC/USD"),
            as_of=rows[-1].closed_utc+timedelta(minutes=8),
            hypothesis=HYPOTHESES[2],costs=COST)
        folds=result["evaluation_folds"]
        self.assertEqual(set(folds),{"development","validation","untouched_test"})
        self.assertEqual(
            folds["development"]["evaluation_end_utc"],
            folds["validation"]["evaluation_start_utc"])
        self.assertEqual(
            folds["validation"]["evaluation_end_utc"],
            folds["untouched_test"]["evaluation_start_utc"])
        self.assertEqual(
            sum(item["evaluation_bar_count"] for item in folds.values()),
            len(rows)-max(HYPOTHESES[2].warmup_bars,2))
        self.assertFalse(result["strategy_validated"])
        self.assertFalse(result["hyperparameter_optimization_performed"])

    def test_index_invalid_and_bad_asset_must_fail_before_backtest(self):
        rows=sample()
        for first,last in ((0,len(rows)),(28,28),(1000,1001)):
            with self.subTest(first=first,last=last),self.assertRaises(ValueError):
                simulate_one_asset(
                    rows,spec=candidate("BTC/USD"),
                    as_of=rows[-1].closed_utc,
                    hypothesis=HYPOTHESES[2],costs=COST,
                    evaluation_start_index=first,evaluation_end_index=last)
        with self.assertRaises(ValueError):
            simulate_one_asset(
                rows,spec=candidate("ETH/USD"),as_of=rows[-1].closed_utc,
                hypothesis=HYPOTHESES[2],costs=COST)


if __name__=="__main__":
    unittest.main()

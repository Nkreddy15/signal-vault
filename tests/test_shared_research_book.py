"""No-network shared-$100 multi-asset portfolio simulation acceptance tests."""
from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.multi_asset_simulation import (
    ExplicitRoundTripCosts, HYPOTHESES, HypothesisKind, ResearchHypothesis,
)
from signal_vault.research_universe import ResearchBar, candidate
from signal_vault.shared_research_book import (
    SharedResearchLimits, simulate_shared_research_book,
)

HOUR=timedelta(hours=1)
START=datetime(2026,9,24,0,tzinfo=timezone.utc)
COST=ExplicitRoundTripCosts(
    Decimal("25"),Decimal("4"),Decimal("10"))
MOMENTUM=ResearchHypothesis(
    HypothesisKind.MOMENTUM,"shared-momentum-v1-fixture",
    lookback_bars=24,entry_return_bps=Decimal("50"),
    exit_return_bps=Decimal("-50"))


def sample(sym, *, prices=None, starts=None):
    if prices is None:
        prices=[Decimal("100")+Decimal(2*i) for i in range(65)]
    if starts is None:
        starts=[START+i*HOUR for i in range(len(prices))]
    now=max(starts)+HOUR+timedelta(minutes=8)
    return tuple(
        ResearchBar(
            sym,start,
            Decimal(str(prices[i])),
            Decimal(str(prices[i]))+Decimal("1"),
            Decimal(str(prices[i]))-Decimal("1"),
            Decimal(str(prices[i])),Decimal("7"),
            "synthetic_"+("iex" if sym=="SPY" else "crypto"),
            now,False)
        for i,start in enumerate(starts)
    )


def run(series,hypotheses=None,calendars=None,costs=None,limits=None):
    hyps=hypotheses or {s:MOMENTUM for s in series}
    assumptions=costs or {s:COST for s in series}
    kwargs={}
    if limits is not None:kwargs["limits"]=limits
    return simulate_shared_research_book(
        series,specs={s:candidate(s) for s in series},
        hypotheses=hyps,assumptions=assumptions,
        as_of=max(b[-1].closed_utc for b in series.values())
              +timedelta(minutes=8),
        equity_calendars=calendars,**kwargs)


class SharedResearchBookTests(unittest.TestCase):
    def test_two_simultaneous_entries_compete_for_one_30usd_exposure(self):
        names=("BTC/USD","ETH/USD","SOL/USD")
        series={sym:sample(sym) for sym in names}
        result=run(series)
        fills=[f for f in result["synthetic_fills"] if f["side"]=="buy"]
        self.assertEqual(len(fills),2)
        self.assertEqual(
            [f["symbol"] for f in fills],["BTC/USD","ETH/USD"])
        self.assertEqual(fills[0]["at_open_utc"],fills[1]["at_open_utc"])
        self.assertEqual(
            sum(Decimal(f["cash_change_usd"]) for f in fills),
            Decimal("-30"))
        self.assertEqual(Decimal(result["cash_usd"]),Decimal("70"))
        self.assertEqual(set(result["open_positions_quantity"]),
                         {"BTC/USD","ETH/USD"})
        self.assertTrue(any(
            r["symbol"]=="SOL/USD" and
            r["code"]=="SHARED_TOTAL_LONG_EXPOSURE_LIMIT"
            for r in result["rejections"]))
        self.assertEqual(result["initial_bankroll_usd"],"100")
        self.assertEqual(result["max_single_buy_usd"],"15")
        self.assertEqual(result["max_total_long_exposure_usd"],"30")
        self.assertEqual(result["broker_order_submission"],"DISABLED")
        self.assertFalse(result["provider_paper_positions_queried"])

    def test_same_timestamp_future_close_cannot_change_initial_entries(self):
        series={sym:sample(sym) for sym in ("BTC/USD","ETH/USD","SOL/USD")}
        initial=run(series)
        first=next(f["at_open_utc"] for f in initial["synthetic_fills"]
                   if f["side"]=="buy")
        a=list(series["BTC/USD"])
        target=next(i for i,b in enumerate(a) if b.start_utc.isoformat()==first)
        a[target]=replace(a[target],close=Decimal("1000"),high=Decimal("1001"))
        mutated=run({**series,"BTC/USD":tuple(a)})
        lhs=[(f["symbol"],f["side"],f["at_open_utc"],f["quantity"],
              f["signal_sha256"]) for f in initial["synthetic_fills"]
             if f["at_open_utc"]==first]
        rhs=[(f["symbol"],f["side"],f["at_open_utc"],f["quantity"],
              f["signal_sha256"]) for f in mutated["synthetic_fills"]
             if f["at_open_utc"]==first]
        self.assertEqual(lhs,rhs)

    def test_cash_only_through_multiple_assets_is_100_not_n_times_100(self):
        series={sym:sample(sym) for sym in ("BTC/USD","ETH/USD","SOL/USD")}
        result=run(series,hypotheses={sym:HYPOTHESES[0] for sym in series})
        self.assertEqual(result["cash_usd"],"100")
        self.assertEqual(result["final_marked_equity_usd"],"100")
        self.assertEqual(result["synthetic_fills"],[])
        self.assertEqual(result["sampled_event_max_drawdown_usd"],"0")

    def test_mixed_equity_and_crypto_are_calendar_validated_separately(self):
        # Deliberately explicit synthetic session timeline; not a provider
        # claim about market hours/holiday/half-session completeness.
        days=[0,1,2,3,4,7,8,9,10,11,14,15]
        opens=tuple(
            datetime(2026,9,14,13,30,tzinfo=timezone.utc)+timedelta(days=d,hours=i)
            for d in days for i in range(6))
        spy=sample("SPY",prices=[100+i for i in range(len(opens))],starts=opens)
        crypto_start=(opens[-1]-timedelta(hours=64)).replace(minute=0)
        eth_times=[crypto_start+i*HOUR for i in range(65)]
        eth=sample("ETH/USD",starts=eth_times)
        with self.assertRaises(ValueError):
            run({"SPY":spy,"ETH/USD":eth})
        out=run({"SPY":spy,"ETH/USD":eth},calendars={"SPY":opens})
        self.assertEqual(set(out["market_feed_by_asset"]),{"SPY","ETH/USD"})
        self.assertGreater(out["evaluated_distinct_next_open_event_times"],0)
        self.assertEqual(out["broker_order_submission"],"DISABLED")

    def test_inconsistent_cap_or_missing_market_cost_fails_closed(self):
        with self.assertRaises(ValueError):
            SharedResearchLimits(maximum_total_long_exposure_usd=Decimal("5"))
        series={"BTC/USD":sample("BTC/USD")}
        with self.assertRaises(ValueError):
            simulate_shared_research_book(
                series,specs={"BTC/USD":candidate("BTC/USD")},
                hypotheses={"BTC/USD":MOMENTUM},
                assumptions={},
                as_of=series["BTC/USD"][-1].closed_utc)

    def test_held_asset_negative_gap_blocks_further_new_entries(self):
        # Synthetic fast reversal after first $15 BUY. No automatic provider
        # SELL is allowed; the risk cap blocks new entries only.
        rises=[Decimal("100")+Decimal(i*2) for i in range(35)]
        crash=[Decimal("15")]*30
        bitcoin=sample("BTC/USD",prices=rises+crash)
        ethereum=sample("ETH/USD",prices=[Decimal("100")]*42 +
                        [Decimal("100")+Decimal(i*5) for i in range(23)])
        result=run({"BTC/USD":bitcoin,"ETH/USD":ethereum})
        self.assertTrue(result["new_entries_gated_by_shared_loss_or_drawdown"])
        self.assertTrue(any(
            r["code"]=="SHARED_DAILY_LOSS_OR_DRAWDOWN_NEW_BUY_BLOCK"
            for r in result["rejections"]))
        self.assertEqual(result["broker_order_submission"],"DISABLED")


if __name__=="__main__":
    unittest.main()

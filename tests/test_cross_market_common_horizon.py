"""Synthetic mixed crypto/XNYS one-bankroll aligned-horizon invariants.

Separate history archives may have entirely different start/end timelines.
With the NEW explicit common evaluation scope, NO $15 research BUY may be
considered before ALL participating instruments have >=28 PRIOR completed
indicator history bars; the earlier-running crypto study cannot silently
consume the entire shared $30 before stocks even enter their first session.
No broker endpoints, credential access, live routing or order submission.
"""
from __future__ import annotations

import unittest
from datetime import datetime,timedelta,timezone
from decimal import Decimal

from signal_vault.multi_asset_simulation import (
    ExplicitRoundTripCosts, HYPOTHESES,
)
from signal_vault.research_universe import ResearchBar,candidate
from signal_vault.shared_research_book import simulate_shared_research_book

UTC=timezone.utc
HOUR=timedelta(hours=1)
EQUITY_START=datetime(2026,9,14,14,tzinfo=UTC)
CRYPTO_START=datetime(2026,9,14,0,tzinfo=UTC)
END=datetime(2026,9,26,0,tzinfo=UTC)
CRYPTO_COST=ExplicitRoundTripCosts(
    Decimal("25"),Decimal("4"),Decimal("10"))
STOCK_COST=ExplicitRoundTripCosts(
    Decimal("0"),Decimal("3"),Decimal("5"))


def source(sym,times,price,feed,now):
    p=Decimal(price)
    return tuple(ResearchBar(
        sym,t,p,p+Decimal("2"),p-Decimal("2"),p,
        Decimal("20"),feed,now,False)
        for t in times)


def aligned_data():
    stock=tuple(
        EQUITY_START+timedelta(days=day,hours=hour)
        for day in (0,1,2,3,4,7,8,9,10,11)
        for hour in range(6))
    crypto=tuple(
        CRYPTO_START+i*HOUR for i in range(12*24))
    assert len(stock)==60 and len(crypto)==288
    return {
        "AAPL":source("AAPL",stock,"200",
                      "synthetic_iex_adjusted",END),
        "BTC/USD":source("BTC/USD",crypto,"100",
                         "synthetic_crypto",END),
    }, {"AAPL":stock}


def run(dataset,grid,**opts):
    return simulate_shared_research_book(
        dataset,specs={sym:candidate(sym) for sym in dataset},
        hypotheses={sym:HYPOTHESES[1] for sym in dataset},
        assumptions={
            sym:(STOCK_COST if sym=="AAPL" else CRYPTO_COST)
            for sym in dataset},
        as_of=END,equity_calendars=grid,**opts)


class CrossMarketCommonHorizonTests(unittest.TestCase):
    def test_two_markets_begin_same_shared_book_after_all_indicators_warm(self):
        data,grids=aligned_data()
        stock_first_eligible=data["AAPL"][28].start_utc
        self.assertEqual(stock_first_eligible,
                         datetime(2026,9,18,18,tzinfo=UTC))
        end=data["AAPL"][-1].closed_utc
        outcome=run(
            data,grids,evaluation_start_utc=stock_first_eligible,
            evaluation_end_utc_exclusive=end)
        self.assertTrue(outcome["global_common_horizon_applied"])
        self.assertEqual(outcome["global_common_start_utc"],
                         stock_first_eligible.isoformat())
        self.assertEqual(outcome["global_common_end_utc_exclusive"],
                         end.isoformat())
        self.assertTrue(outcome["all_asset_indicators_warmed_before_shared_capital_started"])
        self.assertFalse(outcome["pre_horizon_hypothetical_fills_permitted"])
        fills=outcome["synthetic_fills"]
        self.assertEqual(len(fills),2)
        self.assertEqual([r["symbol"] for r in fills],["AAPL","BTC/USD"])
        self.assertEqual({r["at_open_utc"] for r in fills},
                         {stock_first_eligible.isoformat()})
        self.assertEqual(outcome["cash_usd"],"70")
        self.assertEqual(outcome["max_total_long_exposure_usd"],"30")
        self.assertTrue(outcome["estimated_liquidation_not_an_order"])
        self.assertFalse(outcome["cross_market_tradability_or_fractional_share_verified"])
        self.assertEqual(outcome["broker_order_submission"],"DISABLED")

    def test_unscoped_legacy_book_preserves_original_result_shape(self):
        data,grids=aligned_data()
        outcome=run(data,grids)
        self.assertNotIn("global_common_horizon_applied",outcome)
        self.assertNotIn("global_common_start_utc",outcome)
        buys=[r for r in outcome["synthetic_fills"] if r["side"]=="buy"]
        self.assertEqual(buys[0]["symbol"],"BTC/USD")
        self.assertLess(
            datetime.fromisoformat(buys[0]["at_open_utc"]),
            data["AAPL"][28].start_utc)
        self.assertEqual(outcome["broker_order_submission"],"DISABLED")

    def test_reject_early_crypto_allocation_before_later_stock_warmup(self):
        data,grids=aligned_data()
        with self.assertRaisesRegex(ValueError,"unmatched common history"):
            run(data,grids,
                evaluation_start_utc=data["BTC/USD"][28].start_utc,
                evaluation_end_utc_exclusive=data["AAPL"][-1].closed_utc)

    def test_mixed_market_final_mark_never_reaches_future_crypto_only_tail(self):
        data,grids=aligned_data()
        first=data["AAPL"][28].start_utc
        # Sep25 20:00Z is the last stock close: the Sep25 20-23 crypto
        # candles are OUTSIDE this two-market report's common end.
        with self.assertRaisesRegex(ValueError,"unmatched common history"):
            run(data,grids,
                evaluation_start_utc=first,
                evaluation_end_utc_exclusive=data["BTC/USD"][-1].closed_utc)
        valid=run(data,grids,
                  evaluation_start_utc=first,
                  evaluation_end_utc_exclusive=data["AAPL"][-1].closed_utc)
        self.assertEqual(valid["broker_order_submission"],"DISABLED")
        self.assertTrue(valid["the_end_of_the_shortest_market_stops_joint_marking"])

    def test_missing_one_bound_naive_and_nonoverlapping_source_horizons_refused(self):
        data,grid=aligned_data()
        first=data["AAPL"][28].start_utc
        last=data["AAPL"][-1].closed_utc
        cases=(
            dict(evaluation_start_utc=first),
            dict(evaluation_end_utc_exclusive=last),
            dict(evaluation_start_utc=first.replace(tzinfo=None),
                 evaluation_end_utc_exclusive=last),
            dict(evaluation_start_utc=first,
                 evaluation_end_utc_exclusive=last.replace(tzinfo=None)),
        )
        for case in cases:
            with self.subTest(case=case),self.assertRaises(ValueError):
                run(data,grid,**case)

        # The historical crypto download ending 2026-09-01 cannot be
        # forward-filled to become the Sept14+ XNYS stock experiment.
        old_crypto=tuple(datetime(2026,8,20,tzinfo=UTC)+i*HOUR
                         for i in range(12*24))
        old={
            "AAPL":data["AAPL"],
            "BTC/USD":source("BTC/USD",old_crypto,"100",
                             "synthetic_crypto",END),
        }
        with self.assertRaises(ValueError):
            run(old,grid,evaluation_start_utc=first,
                evaluation_end_utc_exclusive=last)


if __name__=="__main__":
    unittest.main()

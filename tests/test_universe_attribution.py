"""Offline-only six-crypto attribution & passive-pair concentration tests."""
from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.multi_asset_simulation import (
    ExplicitRoundTripCosts, HYPOTHESES,
)
from signal_vault.research_universe import ResearchBar
from signal_vault.shared_research_book import simulate_shared_research_book
from signal_vault.research_universe import candidate
from signal_vault.universe_attribution import (
    FIRST_ELIGIBLE_BAR_INDEX, all_pair_passive_diagnostics,
)

START = datetime(2026, 7, 1, 0, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)
BASE = ExplicitRoundTripCosts(Decimal("25"),Decimal("4"),Decimal("10"))


def candles(sym: str, *, count: int=70, scalar: str="1") -> tuple[ResearchBar,...]:
    captured = START+count*HOUR+timedelta(minutes=7)
    scale=Decimal(scalar)
    values=[
        (Decimal("100")+Decimal(i%7)+Decimal(i)/Decimal("10"))*scale
        for i in range(count)
    ]
    return tuple(
        ResearchBar(
            sym,START+i*HOUR,
            values[i],values[i]+scale*Decimal("2"),
            values[i]-scale*Decimal("2"),values[i],
            Decimal("8"),"synthetic_alpaca_crypto_us",
            captured,False,
        )
        for i in range(count)
    )


class PairUniverseAttributionTests(unittest.TestCase):
    def test_all_three_alternatives_without_claiming_a_universe_index(self):
        source={
            "BTC/USD":candles("BTC/USD"),
            "ETH/USD":candles("ETH/USD",scalar="2"),
            "SOL/USD":candles("SOL/USD",scalar="0.5"),
        }
        report=all_pair_passive_diagnostics(
            source,as_of=START+70*HOUR+timedelta(minutes=7),
            costs={sym:BASE for sym in source})
        self.assertEqual(report["all_pair_summary_usd"]["scenario_count"],3)
        self.assertEqual(len(report["all_pair_scenarios"]),3)
        self.assertEqual(len(report["pairwise_hourly_close_return_correlations"]),3)
        self.assertEqual(report["distinct_shared_close_return_hours"],69)
        self.assertEqual(report["alphabetical_pair_represented_by_old_passive_baseline"],
                         ["BTC/USD","ETH/USD"])
        self.assertTrue(report["previous_passive_book_was_not_a_six_asset_index"])
        self.assertFalse(report["asset_selection_based_on_test_period"])
        self.assertEqual(len(report["research_report_sha256"]),64)
        self.assertEqual(
            report,all_pair_passive_diagnostics(
                source,as_of=START+70*HOUR+timedelta(minutes=7),
                costs={sym:BASE for sym in source}))
        self.assertTrue(
            all(pair["hypothetical_uninvested_cash_usd"]=="70"
                and pair["modeled_two_entries_usd"]=="30"
                and pair["broker_order_submission"]=="DISABLED"
                for pair in report["all_pair_scenarios"]))
        self.assertEqual(report["broker_order_submission"],"DISABLED")

    def test_original_shared_passive_matches_first_alphabetical_pair_to_cent(self):
        source={
            sym:candles(sym,scalar=mult)
            for sym,mult in (("BTC/USD","1"),("ETH/USD","2"),("SOL/USD","0.5"))
        }
        costs={sym:BASE for sym in source}
        as_of=START+70*HOUR+timedelta(minutes=7)
        outcome=all_pair_passive_diagnostics(source,as_of=as_of,costs=costs)
        first_pair=outcome["all_pair_scenarios"][0]
        self.assertEqual(first_pair["symbols"],["BTC/USD","ETH/USD"])
        self.assertEqual(
            first_pair["first_eligible_reference_open_utc"],
            (START+FIRST_ELIGIBLE_BAR_INDEX*HOUR).isoformat())
        book=simulate_shared_research_book(
            source,specs={sym:candidate(sym) for sym in source},
            hypotheses={sym:HYPOTHESES[1] for sym in source},
            assumptions=costs,as_of=as_of)
        self.assertEqual(len(book["synthetic_fills"]),2)
        self.assertEqual(
            Decimal(first_pair["unrounded_net_pnl_if_liquidated_usd"]),
            Decimal(book["net_pnl_if_hypothetically_liquidated_usd"]))

    def test_all_six_assets_generate_fifteen_alternatives_not_six_simultaneous_buys(self):
        source={sym:candles(sym,scalar=str(i+1))
                for i,sym in enumerate(("BTC/USD","ETH/USD","SOL/USD",
                                         "LTC/USD","LINK/USD","AVAX/USD"))}
        report=all_pair_passive_diagnostics(
            source,as_of=START+70*HOUR+timedelta(minutes=7),
            costs={sym:BASE for sym in source})
        self.assertEqual(report["all_pair_summary_usd"]["scenario_count"],15)
        self.assertEqual(len(report["assets"]),6)
        self.assertEqual(report["initial_bankroll_usd_per_ALTERNATIVE_scenario"],"100")
        self.assertEqual(report["each_pair_invested_usd"],"30")
        # All scaled copies have identical simple percentage return series.
        self.assertTrue(all(
            pair["hourly_close_return_pearson"]==1.0
            for pair in report["pairwise_hourly_close_return_correlations"]))

    def test_constant_price_series_have_undefined_not_fabricated_correlation(self):
        x=list(candles("BTC/USD"))
        y=list(candles("ETH/USD"))
        def flat(b):
            return replace(b,open=Decimal("100"),high=Decimal("101"),
                           low=Decimal("99"),close=Decimal("100"))
        source={"BTC/USD":tuple(map(flat,x)),
                "ETH/USD":tuple(map(flat,y))}
        output=all_pair_passive_diagnostics(
            source,as_of=START+70*HOUR+timedelta(minutes=7),
            costs={sym:BASE for sym in source})
        self.assertIsNone(
            output["pairwise_hourly_close_return_correlations"][0]
                  ["hourly_close_return_pearson"])

    def test_gap_feed_difference_misaligned_or_prospective_history_fail_closed(self):
        base=candles("BTC/USD")
        eth=candles("ETH/USD")
        scenarios=(
            (base,eth[:40]+eth[41:]),
            (base,tuple(replace(bar,feed="different_source") for bar in eth)),
            (base,tuple(replace(bar,start_utc=bar.start_utc+HOUR)
                        for bar in eth)),
            (base,tuple(replace(bar,prospective=True) for bar in eth)),
        )
        for a,b in scenarios:
            with self.subTest(kind=(len(b),b[0].feed,b[0].start_utc,
                                    b[0].prospective)),self.assertRaises(ValueError):
                all_pair_passive_diagnostics(
                    {"BTC/USD":a,"ETH/USD":b},
                    as_of=START+71*HOUR+timedelta(minutes=7),
                    costs={"BTC/USD":BASE,"ETH/USD":BASE})
        with self.assertRaises(ValueError):
            all_pair_passive_diagnostics(
                {"BTC/USD":base,"ETH/USD":eth},
                as_of=START+70*HOUR+timedelta(minutes=7),
                costs={"BTC/USD":BASE})


if __name__=="__main__":
    unittest.main()

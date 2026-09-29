"""Pure cost-aware multi-asset directional shadow, zero broker/network."""
from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from decimal import Decimal

from signal_vault.multi_asset_shadow_scan import (
    illustrative_break_even,offline_universe_shadow_scan,
)
from signal_vault.multi_asset_simulation import (
    ExplicitRoundTripCosts,HYPOTHESES,HypothesisKind,ResearchHypothesis,
)
from signal_vault.research_universe import ResearchBar

START=datetime(2026,9,20,tzinfo=timezone.utc)
HOUR=timedelta(hours=1)
AS_OF=START+72*HOUR


def history(sym,prices=None,starts=None):
    if prices is None:prices=[Decimal("100")+Decimal(i*2) for i in range(70)]
    if starts is None:starts=[START+i*HOUR for i in range(len(prices))]
    captured=max(starts)+HOUR+timedelta(minutes=7)
    return tuple(
        ResearchBar(
            sym,t,Decimal(str(prices[i])),Decimal(str(prices[i]))+1,
            Decimal(str(prices[i]))-1,Decimal(str(prices[i])),
            Decimal("10"),"synthetic_provider",captured,False)
        for i,t in enumerate(starts))


class OfflineMultimarketShadowTests(unittest.TestCase):
    def test_higher_costs_increase_break_even_and_no_future_quote_implied(self):
        zero=ExplicitRoundTripCosts(
            Decimal("0"),Decimal("0"),Decimal("0"))
        heavy=ExplicitRoundTripCosts(
            Decimal("25"),Decimal("6"),Decimal("10"))
        a=illustrative_break_even(zero)
        b=illustrative_break_even(heavy)
        self.assertEqual(a["break_even_gross_mid_move_bps_up"],"0.00")
        self.assertEqual(a["gross_mid_move_for_target_bps_up"],"20.00")
        self.assertGreater(
            Decimal(b["break_even_gross_mid_move_bps_up"]),
            Decimal(a["break_even_gross_mid_move_bps_up"]))
        self.assertTrue(b["assumptions_are_estimates_not_market_quotes"])

    def test_three_asset_snapshot_all_directional_buy_signals_hold_without_edge_proof(self):
        series={s:history(s) for s in ("BTC/USD","ETH/USD","SOL/USD")}
        costs={s:ExplicitRoundTripCosts(
            Decimal("25"),Decimal("4"),Decimal("10")) for s in series}
        snap=offline_universe_shadow_scan(
            series,as_of=AS_OF,costs=costs,
            hypotheses=HYPOTHESES)
        self.assertEqual(len(snap["assets"]),3)
        self.assertEqual(len(snap["combined_report_sha256"]),64)
        self.assertEqual(snap["broker_order_submission"],"DISABLED")
        self.assertTrue(snap["no_network_or_keychain_requests"])
        self.assertTrue(snap["no_historical_data_upgraded_to_forward_proof"])
        self.assertEqual(
            snap,offline_universe_shadow_scan(
                series,as_of=AS_OF,costs=costs,hypotheses=HYPOTHESES))
        for asset in snap["assets"]:
            self.assertEqual(asset["historical_and_provisional_prospective_counts"]
                             ["historical"],70)
            self.assertEqual(asset["historical_and_provisional_prospective_counts"]
                             ["timestamp_plausible_prospective_not_archive_verified"],0)
            self.assertEqual(asset["hypotheses"][1]["cost_aware_research_only_entry"],
                             "REFERENCE_BASELINE_NO_AUTOMATIC_SIGNALS")
            self.assertEqual(asset["hypotheses"][3]["flat_scenario_direction"],"buy")
            self.assertEqual(asset["hypotheses"][3]["cost_aware_research_only_entry"],
                             "HOLD_BUY_VETO_NO_INDEPENDENT_FORWARD_EDGE")
            self.assertTrue(all(
                decision["broker_order_submission"]=="DISABLED"
                for decision in asset["hypotheses"]))

    def test_last_bar_change_changes_sha_but_never_enables_trading(self):
        original={"BTC/USD":history("BTC/USD")}
        costs={"BTC/USD":ExplicitRoundTripCosts(
            Decimal("25"),Decimal("4"),Decimal("10"))}
        first=offline_universe_shadow_scan(original,as_of=AS_OF,costs=costs)
        bars=list(original["BTC/USD"])
        bars[-1]=replace(bars[-1],close=Decimal("250"),
                         high=Decimal("251"))
        second=offline_universe_shadow_scan(
            {"BTC/USD":tuple(bars)},as_of=AS_OF,costs=costs)
        self.assertNotEqual(first["combined_report_sha256"],
                            second["combined_report_sha256"])
        self.assertEqual(second["broker_order_submission"],"DISABLED")

    def test_equity_scan_requires_operator_verified_calendar(self):
        starts=tuple(datetime(2026,9,21,13,30,tzinfo=timezone.utc)
                     +timedelta(days=d,hours=i)
                     for d in range(10) for i in range(6))
        spy=history("SPY",prices=[Decimal("100")]*len(starts),starts=starts)
        costs={"SPY":ExplicitRoundTripCosts(
            Decimal("0"),Decimal("2"),Decimal("5"))}
        with self.assertRaises(ValueError):
            offline_universe_shadow_scan(
                {"SPY":spy},as_of=spy[-1].closed_utc+timedelta(minutes=8),
                costs=costs)
        report=offline_universe_shadow_scan(
            {"SPY":spy},as_of=spy[-1].closed_utc+timedelta(minutes=8),
            costs=costs,equity_calendars={"SPY":starts})
        self.assertTrue(report["assets"][0]
                        ["no_next_execution_timestamp_inferred_for_equity"])

    def test_cost_and_length_gates_fail_closed(self):
        series={"BTC/USD":history("BTC/USD")[:20]}
        costs={"BTC/USD":ExplicitRoundTripCosts(
            Decimal("25"),Decimal("4"),Decimal("10"))}
        with self.assertRaises(ValueError):
            offline_universe_shadow_scan(series,as_of=AS_OF,costs=costs)
        with self.assertRaises(ValueError):
            offline_universe_shadow_scan(
                {"BTC/USD":history("BTC/USD")},
                as_of=AS_OF,costs={})


if __name__=="__main__":
    unittest.main()

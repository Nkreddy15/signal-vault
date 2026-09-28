import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.backtest import ResearchFold, simulate
from signal_vault.market_data import Bar
from signal_vault.research_gate import ResearchGatePolicy, assess_research_folds
from signal_vault.strategy import StrategyConfig

START=datetime(2026,1,1,tzinfo=timezone.utc)


def baseline_result():
    bars=[]
    values=[100]*8+[90]*8+[120]*8+[80]*10
    for i,x in enumerate(values):
        v=Decimal(x)
        bars.append(Bar(START+timedelta(hours=i),v,v+1,v-1,v,Decimal(1),"gate-test"))
    return simulate(bars,as_of=bars[-1].close_time,strategy=StrategyConfig(3,5))


def folds_with(result,n=8):
    return tuple(ResearchFold(f"s{i}",f"e{i}",7,result) for i in range(n))


class ResearchGateTests(unittest.TestCase):
    def test_single_lucky_window_never_passes(self):
        r=replace(baseline_result(),net_pnl_usd=Decimal("5"),
                  passive_same_allocation_net_pnl_usd=Decimal("1"),
                  max_drawdown_usd=Decimal("1"),fills=baseline_result().fills*5)
        result=assess_research_folds(folds_with(r,1))
        self.assertFalse(result.passed)
        self.assertIn("insufficient disjoint evaluation folds",result.reasons)

    def test_predeclared_good_synthetic_set_can_pass_gate(self):
        base=baseline_result()
        # Synthetic unit fixture only; this does not assert a real strategy edge.
        fills=(base.fills or ()) * 2
        if len(fills)<2:
            self.skipTest("synthetic base did not generate enough fills")
        r=replace(base,net_pnl_usd=Decimal("1"),
                  passive_same_allocation_net_pnl_usd=Decimal("0.2"),
                  max_drawdown_usd=Decimal("2"),fills=fills)
        policy=ResearchGatePolicy(minimum_fills=min(10,len(fills)*8))
        result=assess_research_folds(folds_with(r,8),policy)
        self.assertTrue(result.passed,result.reasons)
        self.assertEqual(result.to_dict()["kind"],"OFFLINE_RESEARCH_GATE_NOT_LIVE_AUTHORIZATION")

    def test_passive_underperformance_and_drawdown_fail(self):
        base=baseline_result()
        r=replace(base,net_pnl_usd=Decimal("1"),
                  passive_same_allocation_net_pnl_usd=Decimal("2"),
                  max_drawdown_usd=Decimal("11"),fills=base.fills*6)
        result=assess_research_folds(folds_with(r,8),ResearchGatePolicy(minimum_fills=1))
        self.assertFalse(result.passed)
        self.assertTrue(any("passive" in x for x in result.reasons))
        self.assertTrue(any("drawdown" in x for x in result.reasons))

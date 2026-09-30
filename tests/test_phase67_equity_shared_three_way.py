import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.ci_historical_equities import SYMBOLS
from signal_vault.offline_equity_shared_three_way import (
    shared_equity_three_way_research,
)
from signal_vault.research_universe import ResearchBar

UTC=timezone.utc
START=datetime(2026,1,5,15,tzinfo=UTC)


def synthetic(hours=200):
    grid=tuple(START+timedelta(hours=i) for i in range(hours))
    datasets={}
    for s_idx,symbol in enumerate(SYMBOLS):
        base=Decimal(100+s_idx*10)
        rows=[]
        for i,at in enumerate(grid):
            wave=Decimal((i%18)-9)/Decimal("20")
            drift=Decimal(i)/Decimal("250")
            close=base+wave+drift
            rows.append(ResearchBar(
                symbol=symbol,
                start_utc=at,
                open=close,
                high=close+Decimal("1"),
                low=close-Decimal("1"),
                close=close,
                volume=Decimal("1000"),
                feed="alpaca_equity_iex|adjustment=all",
                captured_utc=at+timedelta(hours=1,minutes=5),
                prospective=False,
            ))
        datasets[symbol]=tuple(rows)
    return datasets,grid


class SharedEquityThreeWayResearchTests(unittest.TestCase):
    def test_shared_book_uses_fixed_warmup_and_separate_untouched_fold(self):
        datasets,grid=synthetic()
        result=shared_equity_three_way_research(
            datasets,timeline=grid,as_of=grid[-1]+timedelta(hours=2)
        )
        self.assertEqual(result["warmup_core_hours"],60)
        self.assertEqual(
            result["fold_core_hours"],
            {"development":84,"validation":28,"untouched_test":28},
        )
        self.assertEqual(result["shared_bankroll_usd"],"100")
        self.assertFalse(result["untouched_test_used_for_strategy_selection"])
        self.assertFalse(result["strategy_ranking_performed"])
        self.assertFalse(result["strategy_selection_performed"])
        self.assertFalse(result["hyperparameter_optimization_performed"])
        self.assertEqual(result["broker_order_submission"],"DISABLED")
        self.assertEqual(result["live_trading"],"UNAVAILABLE")

        scenarios=result["three_fixed_friction_scenarios"]
        self.assertEqual(len(scenarios),3)
        for scenario in scenarios.values():
            self.assertEqual(len(scenario["hypotheses"]),4)
            for folds in scenario["hypotheses"].values():
                self.assertEqual(
                    set(folds),
                    {"development","validation","untouched_test"},
                )
                self.assertEqual(folds["development"]["evaluation_core_hours"],84)
                self.assertEqual(folds["validation"]["evaluation_core_hours"],28)
                self.assertEqual(folds["untouched_test"]["evaluation_core_hours"],28)

    def test_too_short_misaligned_or_wrong_universe_fails_closed(self):
        datasets,grid=synthetic(hours=179)
        with self.assertRaises(ValueError):
            shared_equity_three_way_research(
                datasets,timeline=grid,as_of=grid[-1]+timedelta(hours=2)
            )

        datasets,grid=synthetic()
        broken=dict(datasets)
        broken["AAPL"]=broken["AAPL"][:-1]
        with self.assertRaises(ValueError):
            shared_equity_three_way_research(
                broken,timeline=grid,as_of=grid[-1]+timedelta(hours=2)
            )

        broken=dict(datasets)
        broken.pop("AMD")
        with self.assertRaises(ValueError):
            shared_equity_three_way_research(
                broken,timeline=grid,as_of=grid[-1]+timedelta(hours=2)
            )


if __name__=="__main__":
    unittest.main()

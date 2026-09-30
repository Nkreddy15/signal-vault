import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.ci_historical_equities import SYMBOLS
from signal_vault.offline_equity_walk_forward import expanding_equity_walk_forward
from signal_vault.research_universe import ResearchBar

UTC = timezone.utc
START = datetime(2026, 1, 5, 15, tzinfo=UTC)


def synthetic_equities(hours=180):
    grid = tuple(START + timedelta(hours=i) for i in range(hours))
    datasets = {}
    for symbol_index, symbol in enumerate(SYMBOLS):
        rows = []
        base = Decimal(100 + symbol_index * 20)
        for i, at in enumerate(grid):
            # Deterministic changing prices exercise signals without using any
            # future value in the strategy implementation.
            wave = Decimal((i % 24) - 12) / Decimal("20")
            drift = Decimal(i) / Decimal("200")
            close = base + drift + wave
            rows.append(
                ResearchBar(
                    symbol=symbol,
                    start_utc=at,
                    open=close,
                    high=close + Decimal("1"),
                    low=close - Decimal("1"),
                    close=close,
                    volume=Decimal("1000"),
                    feed="alpaca_equity_iex|adjustment=all",
                    captured_utc=at + timedelta(hours=1, minutes=5),
                    prospective=False,
                )
            )
        datasets[symbol] = tuple(rows)
    return datasets, grid


class EquityExpandingWalkForwardTests(unittest.TestCase):
    def test_fixed_hypotheses_run_on_repeated_later_blocks_without_selection(self):
        datasets, grid = synthetic_equities()
        result = expanding_equity_walk_forward(
            datasets,
            grid=grid,
            as_of=grid[-1] + timedelta(hours=2),
            initial_train_count=90,
            validation_count=30,
            step_count=30,
        )
        self.assertEqual(result["fold_count"], 3)
        self.assertTrue(result["historical_walk_forward_complete"])
        self.assertTrue(result["historical_walk_forward_is_not_prospective_validation"])
        self.assertFalse(result["strategy_selection_performed"])
        self.assertFalse(result["hyperparameter_optimization_performed"])
        self.assertEqual(result["prospective_observations_verified"], 0)
        self.assertEqual(result["automatic_strategy_promotion"], "DISABLED")
        self.assertEqual(result["broker_order_submission"], "DISABLED")
        self.assertEqual(result["live_trading"], "UNAVAILABLE")

        for scenario in result["three_fixed_friction_scenarios"].values():
            self.assertEqual(
                set(scenario["hypotheses"]),
                set(result["all_hypotheses_predeclared"]),
            )
            for hypothesis in scenario["hypotheses"].values():
                self.assertEqual(hypothesis["fold_count"], 3)
                self.assertFalse(hypothesis["strategy_selected_from_fold_results"])
                self.assertFalse(hypothesis["hyperparameter_tuning_from_fold_results"])
                starts = [fold["validation_start_utc"] for fold in hypothesis["folds"]]
                self.assertEqual(starts, sorted(starts))
                self.assertEqual(
                    [fold["train_context_core_hours"] for fold in hypothesis["folds"]],
                    [90, 120, 150],
                )
                self.assertTrue(
                    all(fold["validation_core_hours"] == 30 for fold in hypothesis["folds"])
                )

    def test_future_or_misaligned_data_and_tiny_windows_fail_closed(self):
        datasets, grid = synthetic_equities()
        with self.assertRaises(ValueError):
            expanding_equity_walk_forward(
                datasets,
                grid=grid,
                as_of=grid[-1] + timedelta(hours=2),
                initial_train_count=30,
                validation_count=30,
                step_count=30,
            )
        broken = dict(datasets)
        broken["AAPL"] = broken["AAPL"][:-1]
        with self.assertRaises(ValueError):
            expanding_equity_walk_forward(
                broken,
                grid=grid,
                as_of=grid[-1] + timedelta(hours=2),
                initial_train_count=90,
                validation_count=30,
                step_count=30,
            )


if __name__ == "__main__":
    unittest.main()

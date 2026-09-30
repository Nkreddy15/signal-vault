import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.ci_historical_equities import SYMBOLS
from signal_vault.equity_prospective_shadow_gate import (
    assess_equity_prospective_shadow,
)
from signal_vault.equity_prospective_shadow_summary import (
    build_equity_prospective_shadow_summary,
)
from signal_vault.research_universe import ResearchBar


UTC = timezone.utc
CANDIDATE = "generic-momentum24bar50bps-v1-predeclared"


def twenty_weekday_core_hours():
    days = []
    cursor = date(2026, 8, 3)
    while len(days) < 20:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    grid = []
    for day in days:
        for hour in range(14, 20):
            grid.append(
                datetime(day.year, day.month, day.day, hour, 0, tzinfo=UTC)
            )
    return tuple(grid)


def rows_for(symbol, grid, *, prospective):
    offset = Decimal(str(SYMBOLS.index(symbol) * 2))
    output = []
    for idx, opened in enumerate(grid):
        base = Decimal("100") + offset + Decimal(idx) * Decimal("0.12")
        output.append(
            ResearchBar(
                symbol=symbol,
                start_utc=opened,
                open=base,
                high=base + Decimal("1"),
                low=base - Decimal("1"),
                close=base + Decimal("0.08"),
                volume=Decimal("1000") + Decimal(idx),
                feed="alpaca_equity_iex|adjustment=all",
                captured_utc=(
                    opened + timedelta(hours=1, minutes=7)
                    if prospective
                    else opened + timedelta(hours=2)
                ),
                prospective=prospective,
            )
        )
    return tuple(output)


def historical_confirmation():
    return {
        "kind": "EQUITY_UNTOUCHED_TEST_CONFIRMATION_NO_ORDER",
        "candidate_added_by_untouched_test": False,
        "candidate_ranking_performed": False,
        "automatic_candidate_selection": "DISABLED",
        "paper_order_submission": "DISABLED",
        "live_order_submission": "DISABLED",
        "candidates_confirmed_on_untouched_test": [CANDIDATE],
    }


def source_audit(hours=60):
    return {
        "kind": "EQUITY_FORWARD_ARCHIVE_AUDIT_NO_ORDERS",
        "source_integrity_passed": True,
        "historical_backfill_count": 0,
        "current_segment_hidden_gap_or_interpolation_count": 0,
        "current_segment_complete_six_stock_grid_verified": True,
        "current_segment_prospective_core_hours_per_asset": hours,
        "network_requests": "NONE",
        "broker_order_submission": "DISABLED",
        "live_order_submission": "DISABLED",
    }


class EquityProspectiveShadowSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        grid = twenty_weekday_core_hours()
        cls.warm_grid = grid[:60]
        cls.forward_grid = grid[60:120]
        cls.warm = {
            symbol: rows_for(symbol, cls.warm_grid, prospective=False)
            for symbol in SYMBOLS
        }
        cls.forward = {
            symbol: rows_for(symbol, cls.forward_grid, prospective=True)
            for symbol in SYMBOLS
        }
        cls.as_of = cls.forward_grid[-1] + timedelta(hours=2)

    def test_exact_60_forward_hours_produce_two_fixed_blocks_and_no_orders(self):
        result = build_equity_prospective_shadow_summary(
            historical_confirmation(),
            source_audit(),
            warmup_datasets=self.warm,
            warmup_grid=self.warm_grid,
            prospective_datasets=self.forward,
            prospective_grid=self.forward_grid,
            as_of=self.as_of,
        )
        self.assertEqual(
            result["kind"],
            "EQUITY_PROSPECTIVE_SHADOW_SUMMARY_NO_ORDERS",
        )
        self.assertEqual(result["prospective_core_hours_per_asset"], 60)
        self.assertEqual(result["historical_warmup_core_hours"], 60)
        self.assertFalse(result["historical_warmup_counted_as_prospective"])
        self.assertEqual(result["distinct_xnys_sessions"], 10)
        self.assertEqual(
            set(result["candidate_results"]),
            {CANDIDATE},
        )
        for scenario in (
            "illustrative_base_equity_friction",
            "illustrative_high_equity_friction",
        ):
            candidate = result["candidate_results"][CANDIDATE][scenario]
            passive = result["passive_benchmark_results"][scenario]
            self.assertEqual(len(candidate["chronological_blocks"]), 2)
            self.assertEqual(len(passive["chronological_blocks"]), 2)
            self.assertEqual(
                [x["core_hours"] for x in candidate["chronological_blocks"]],
                [30, 30],
            )
        self.assertEqual(result["network_methods"], ["GET"])
        self.assertEqual(result["paper_order_submission"], "DISABLED")
        self.assertEqual(result["live_order_submission"], "DISABLED")
        self.assertFalse(result["candidate_ranking_performed"])

    def test_summary_is_accepted_by_frozen_phase70_gate_without_authorizing_orders(self):
        summary = build_equity_prospective_shadow_summary(
            historical_confirmation(),
            source_audit(),
            warmup_datasets=self.warm,
            warmup_grid=self.warm_grid,
            prospective_datasets=self.forward,
            prospective_grid=self.forward_grid,
            as_of=self.as_of,
        )
        gate = assess_equity_prospective_shadow(
            historical_confirmation(),
            summary,
        )
        self.assertEqual(
            gate["kind"],
            "EQUITY_PROSPECTIVE_SHADOW_GATE_NO_ORDER",
        )
        self.assertEqual(gate["paper_order_submission"], "DISABLED")
        self.assertEqual(gate["live_order_submission"], "DISABLED")
        self.assertFalse(gate["candidate_ranking_performed"])
        self.assertFalse(
            gate["historical_data_substituted_for_prospective_evidence"]
        )

    def test_59_forward_hours_are_insufficient_even_with_more_history(self):
        short_grid = self.forward_grid[:-1]
        short_rows = {
            symbol: self.forward[symbol][:-1]
            for symbol in SYMBOLS
        }
        with self.assertRaises(ValueError):
            build_equity_prospective_shadow_summary(
                historical_confirmation(),
                source_audit(59),
                warmup_datasets=self.warm,
                warmup_grid=self.warm_grid,
                prospective_datasets=short_rows,
                prospective_grid=short_grid,
                as_of=self.as_of,
            )

    def test_historical_rows_cannot_be_relabelled_as_prospective(self):
        wrong = {
            symbol: tuple(
                ResearchBar(
                    symbol=bar.symbol,
                    start_utc=bar.start_utc,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                    feed=bar.feed,
                    captured_utc=bar.captured_utc,
                    prospective=False,
                )
                for bar in self.forward[symbol]
            )
            for symbol in SYMBOLS
        }
        with self.assertRaises(ValueError):
            build_equity_prospective_shadow_summary(
                historical_confirmation(),
                source_audit(),
                warmup_datasets=self.warm,
                warmup_grid=self.warm_grid,
                prospective_datasets=wrong,
                prospective_grid=self.forward_grid,
                as_of=self.as_of,
            )

    def test_source_audit_gap_blocks_shadow_summary(self):
        audit = source_audit()
        audit["current_segment_hidden_gap_or_interpolation_count"] = 1
        with self.assertRaises(ValueError):
            build_equity_prospective_shadow_summary(
                historical_confirmation(),
                audit,
                warmup_datasets=self.warm,
                warmup_grid=self.warm_grid,
                prospective_datasets=self.forward,
                prospective_grid=self.forward_grid,
                as_of=self.as_of,
            )


if __name__ == "__main__":
    unittest.main()

"""Build the frozen six-stock prospective shadow summary.

Historical bars are permitted only as pre-start indicator warmup. The evaluated
60 core hours must all be genuine prospective rows from the current clean
forward segment. Every historically confirmed candidate is evaluated
independently against the same passive comparator under the predeclared base
and high equity-friction scenarios.

This module is offline: no credentials, network calls, paper orders or live
orders.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Mapping, Sequence

from .ci_historical_equities import EQUITY_ESTIMATED_COST_SCENARIOS, SYMBOLS
from .equity_historical_candidate_gate import PASSIVE, REQUIRED_SCENARIOS
from .multi_asset_simulation import (
    ExplicitRoundTripCosts,
    HYPOTHESES,
    ResearchHypothesis,
)
from .research_universe import ResearchBar, candidate
from .shared_research_book import simulate_shared_research_book

WARMUP_CORE_HOURS = 60
PROSPECTIVE_CORE_HOURS = 60
BLOCK_CORE_HOURS = 30
EXPECTED_BLOCKS = 2


def _utc(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("timezone-aware stock shadow timestamp required")
    return value.astimezone(timezone.utc)


def _hypothesis(name: str) -> ResearchHypothesis:
    matches = tuple(item for item in HYPOTHESES if item.name == name)
    if len(matches) != 1:
        raise ValueError("unknown or non-predeclared stock hypothesis")
    return matches[0]


def _validate_grid(
    datasets: Mapping[str, Sequence[ResearchBar]],
    grid: Sequence[datetime],
    *,
    prospective: bool,
) -> dict[str, tuple[ResearchBar, ...]]:
    timeline = tuple(_utc(x) for x in grid)
    if not timeline or timeline != tuple(sorted(set(timeline))):
        raise ValueError("stock shadow grid must be sorted and unique")
    if set(datasets) != set(SYMBOLS):
        raise ValueError("stock shadow requires exact six-stock universe")
    rows = {symbol: tuple(datasets[symbol]) for symbol in SYMBOLS}
    for symbol in SYMBOLS:
        if (
            len(rows[symbol]) != len(timeline)
            or tuple(_utc(bar.start_utc) for bar in rows[symbol]) != timeline
            or any(bar.symbol != symbol for bar in rows[symbol])
            or any(
                bar.feed != "alpaca_equity_iex|adjustment=all"
                for bar in rows[symbol]
            )
            or any(bar.prospective is not prospective for bar in rows[symbol])
        ):
            raise ValueError("stock shadow rows do not match verified grid/provenance")
    return rows


def _book_receipt(book: Mapping[str, object]) -> dict[str, object]:
    fills = book.get("synthetic_fills")
    if not isinstance(fills, list):
        raise ValueError("stock shadow book lacks synthetic fill list")
    halt = book.get("persistent_peak_drawdown_entry_halt")
    if type(halt) is not bool:
        raise ValueError("stock shadow book lacks persistent halt state")
    return {
        "net_pnl_if_hypothetically_liquidated_usd":
            book["net_pnl_if_hypothetically_liquidated_usd"],
        "sampled_event_max_drawdown_usd":
            book["sampled_event_max_drawdown_usd"],
        "synthetic_fill_count": len(fills),
        "persistent_peak_drawdown_entry_halt": halt,
    }


def _simulate(
    rows: Mapping[str, Sequence[ResearchBar]],
    grid: Sequence[datetime],
    *,
    hypothesis: ResearchHypothesis,
    costs: ExplicitRoundTripCosts,
    as_of: datetime,
    start: datetime,
    end_exclusive: datetime,
) -> dict[str, object]:
    result = simulate_shared_research_book(
        rows,
        specs={symbol: candidate(symbol) for symbol in SYMBOLS},
        hypotheses={symbol: hypothesis for symbol in SYMBOLS},
        assumptions={symbol: costs for symbol in SYMBOLS},
        as_of=as_of,
        equity_calendars={symbol: tuple(grid) for symbol in SYMBOLS},
        evaluation_start_utc=start,
        evaluation_end_utc_exclusive=end_exclusive,
    )
    if (
        result.get("broker_order_submission") != "DISABLED"
        or result.get("live_trading") != "UNAVAILABLE"
        or result.get("past_data_does_not_prove_strategy_edge") is not True
    ):
        raise ValueError("stock prospective simulation escaped research-only contract")
    return _book_receipt(result)


def build_equity_prospective_shadow_summary(
    historical_confirmation: Mapping[str, object],
    source_audit: Mapping[str, object],
    *,
    warmup_datasets: Mapping[str, Sequence[ResearchBar]],
    warmup_grid: Sequence[datetime],
    prospective_datasets: Mapping[str, Sequence[ResearchBar]],
    prospective_grid: Sequence[datetime],
    as_of: datetime,
) -> dict[str, object]:
    if (
        historical_confirmation.get("kind")
        != "EQUITY_UNTOUCHED_TEST_CONFIRMATION_NO_ORDER"
        or historical_confirmation.get("candidate_added_by_untouched_test") is not False
        or historical_confirmation.get("candidate_ranking_performed") is not False
        or historical_confirmation.get("automatic_candidate_selection") != "DISABLED"
        or historical_confirmation.get("paper_order_submission") != "DISABLED"
        or historical_confirmation.get("live_order_submission") != "DISABLED"
    ):
        raise ValueError("invalid frozen stock historical confirmation")
    confirmed = historical_confirmation.get(
        "candidates_confirmed_on_untouched_test"
    )
    if (
        not isinstance(confirmed, list)
        or not confirmed
        or any(not isinstance(x, str) or not x for x in confirmed)
        or len(set(confirmed)) != len(confirmed)
    ):
        raise ValueError("no unique historically confirmed stock candidate")
    for name in confirmed:
        _hypothesis(name)

    if (
        source_audit.get("kind") != "EQUITY_FORWARD_ARCHIVE_AUDIT_NO_ORDERS"
        or source_audit.get("source_integrity_passed") is not True
        or source_audit.get("historical_backfill_count") != 0
        or source_audit.get("current_segment_hidden_gap_or_interpolation_count") != 0
        or source_audit.get("current_segment_complete_six_stock_grid_verified") is not True
        or source_audit.get("network_requests") != "NONE"
        or source_audit.get("broker_order_submission") != "DISABLED"
        or source_audit.get("live_order_submission") != "DISABLED"
    ):
        raise ValueError("invalid stock prospective source audit")

    checked_at = _utc(as_of)
    warm_grid = tuple(_utc(x) for x in warmup_grid)
    prospective_all = tuple(_utc(x) for x in prospective_grid)
    if len(warm_grid) < WARMUP_CORE_HOURS:
        raise ValueError("stock prospective shadow needs fixed historical warmup")
    if len(prospective_all) < PROSPECTIVE_CORE_HOURS:
        raise ValueError("stock prospective shadow does not yet have 60 core hours")
    if source_audit.get("current_segment_prospective_core_hours_per_asset") != len(
        prospective_all
    ):
        raise ValueError("stock source audit and supplied prospective grid differ")

    warm_rows_all = _validate_grid(
        warmup_datasets, warm_grid, prospective=False
    )
    prospective_rows_all = _validate_grid(
        prospective_datasets, prospective_all, prospective=True
    )

    selected_warm_grid = warm_grid[-WARMUP_CORE_HOURS:]
    selected_forward_grid = prospective_all[:PROSPECTIVE_CORE_HOURS]
    if selected_warm_grid[-1] >= selected_forward_grid[0]:
        raise ValueError("historical warmup overlaps prospective stock evidence")
    if selected_forward_grid[-1] + timedelta(hours=1) > checked_at:
        raise ValueError("stock prospective shadow contains unclosed evidence")

    selected_rows: dict[str, tuple[ResearchBar, ...]] = {}
    for symbol in SYMBOLS:
        warm_index = len(warm_rows_all[symbol]) - WARMUP_CORE_HOURS
        selected_rows[symbol] = (
            tuple(warm_rows_all[symbol][warm_index:])
            + tuple(prospective_rows_all[symbol][:PROSPECTIVE_CORE_HOURS])
        )
    combined_grid = selected_warm_grid + selected_forward_grid
    if any(
        tuple(_utc(x.start_utc) for x in selected_rows[symbol]) != combined_grid
        for symbol in SYMBOLS
    ):
        raise ValueError("stock warmup/prospective concatenation changed source clock")

    session_dates = tuple(sorted({x.date() for x in selected_forward_grid}))
    scenario_costs: dict[str, ExplicitRoundTripCosts] = {}
    for scenario in REQUIRED_SCENARIOS:
        raw = EQUITY_ESTIMATED_COST_SCENARIOS[scenario]
        scenario_costs[scenario] = ExplicitRoundTripCosts(
            Decimal(raw["taker_fee_bps"]),
            Decimal(raw["full_spread_bps"]),
            Decimal(raw["slippage_per_side_bps"]),
        )

    def evaluate_hypothesis(hypothesis: ResearchHypothesis) -> dict[str, object]:
        scenarios: dict[str, object] = {}
        for scenario, costs in scenario_costs.items():
            total = _simulate(
                selected_rows,
                combined_grid,
                hypothesis=hypothesis,
                costs=costs,
                as_of=checked_at,
                start=selected_forward_grid[0],
                end_exclusive=selected_forward_grid[-1] + timedelta(hours=1),
            )
            blocks = []
            for block in range(EXPECTED_BLOCKS):
                first = block * BLOCK_CORE_HOURS
                last = first + BLOCK_CORE_HOURS
                receipt = _simulate(
                    selected_rows,
                    combined_grid,
                    hypothesis=hypothesis,
                    costs=costs,
                    as_of=checked_at,
                    start=selected_forward_grid[first],
                    end_exclusive=selected_forward_grid[last - 1] + timedelta(hours=1),
                )
                blocks.append({
                    "block": block + 1,
                    "core_hours": BLOCK_CORE_HOURS,
                    **receipt,
                })
            scenarios[scenario] = {
                **total,
                "chronological_blocks": blocks,
            }
        return scenarios

    candidate_results = {
        name: evaluate_hypothesis(_hypothesis(name))
        for name in confirmed
    }
    passive_results = evaluate_hypothesis(_hypothesis(PASSIVE))

    return {
        "kind": "EQUITY_PROSPECTIVE_SHADOW_SUMMARY_NO_ORDERS",
        "symbols": list(SYMBOLS),
        "historically_confirmed_candidates": list(confirmed),
        "candidate_versions_changed_after_start": False,
        "prospective_core_hours_per_asset": PROSPECTIVE_CORE_HOURS,
        "available_clean_segment_core_hours_per_asset": len(prospective_all),
        "distinct_xnys_sessions": len(session_dates),
        "complete_six_stock_grid_verified": True,
        "historical_warmup_core_hours": WARMUP_CORE_HOURS,
        "historical_warmup_counted_as_prospective": False,
        "historical_backfill_count": 0,
        "hidden_gap_or_interpolation_count": 0,
        "source_integrity_passed": True,
        "candidate_results": candidate_results,
        "passive_benchmark_results": passive_results,
        "network_methods": ["GET"],
        "credentials_accessed": "NONE",
        "broker_order_submission": "DISABLED",
        "paper_order_submission": "DISABLED",
        "live_order_submission": "DISABLED",
        "automatic_candidate_selection": "DISABLED",
        "candidate_ranking_performed": False,
        "live_trading": "UNAVAILABLE",
    }

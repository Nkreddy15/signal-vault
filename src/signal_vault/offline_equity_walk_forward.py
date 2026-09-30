"""Expanding walk-forward evaluation for the fixed six-stock research lane.

This is retrospective historical research only. Every hypothesis is predeclared
before a fold is evaluated; no fold result selects, ranks, tunes, or promotes a
strategy. Each validation block begins strictly after its expanding historical
context and all simulated executions remain next-open, shared-$100, no-order
research.

The source-root entrypoint first requires the Phase 48 immutable long-horizon
source replay to pass, then rechecks its source hashes while reconstructing the
same six-stock XNYS grid.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence

from .ci_historical_equities import EQUITY_ESTIMATED_COST_SCENARIOS, SYMBOLS
from .multi_asset_simulation import ExplicitRoundTripCosts, HYPOTHESES
from .offline_long_equity_validation import (
    MAX_MANIFEST_BYTES,
    MAX_REPORT_BYTES,
    _read_object,
    _stamp,
    validate_long_equity_history,
)
from .offline_multimarket_pipeline import (
    combine_historical_archives,
    read_historical_archive,
)
from .research_universe import ResearchBar, candidate
from .shared_research_book import simulate_shared_research_book

DEFAULT_INITIAL_TRAIN_CORE_HOURS = 120
DEFAULT_VALIDATION_CORE_HOURS = 30
DEFAULT_STEP_CORE_HOURS = 30
MAX_FOLDS = 60


def _positive_count(value: int, *, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def expanding_equity_walk_forward(
    datasets: Mapping[str, Sequence[ResearchBar]],
    *,
    grid: Sequence[datetime],
    as_of: datetime,
    initial_train_count: int = DEFAULT_INITIAL_TRAIN_CORE_HOURS,
    validation_count: int = DEFAULT_VALIDATION_CORE_HOURS,
    step_count: int = DEFAULT_STEP_CORE_HOURS,
) -> dict[str, object]:
    """Evaluate every fixed hypothesis over sequential future historical blocks."""
    initial_train_count = _positive_count(initial_train_count, name="initial_train_count")
    validation_count = _positive_count(validation_count, name="validation_count")
    step_count = _positive_count(step_count, name="step_count")
    if initial_train_count < 60:
        raise ValueError("walk-forward requires at least 60 prior stock core hours")
    if validation_count < 10:
        raise ValueError("walk-forward validation blocks are too small")
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("walk-forward as_of must be timezone-aware")
    checked_at = as_of.astimezone(timezone.utc)

    timeline = tuple(grid)
    if (
        len(timeline) < initial_train_count + validation_count
        or timeline != tuple(sorted(set(timeline)))
        or any(t.tzinfo is None or t.utcoffset() is None for t in timeline)
    ):
        raise ValueError("verified chronological XNYS grid is too small or malformed")
    if set(datasets) != set(SYMBOLS):
        raise ValueError("walk-forward requires the exact six-stock research universe")
    rows = {symbol: tuple(datasets[symbol]) for symbol in SYMBOLS}
    if any(
        len(rows[symbol]) != len(timeline)
        or tuple(bar.start_utc for bar in rows[symbol]) != timeline
        for symbol in SYMBOLS
    ):
        raise ValueError("all stock datasets must match the same verified XNYS grid")

    scenarios: dict[str, object] = {}
    for scenario_name, raw_costs in EQUITY_ESTIMATED_COST_SCENARIOS.items():
        cost = ExplicitRoundTripCosts(
            Decimal(raw_costs["taker_fee_bps"]),
            Decimal(raw_costs["full_spread_bps"]),
            Decimal(raw_costs["slippage_per_side_bps"]),
        )
        hypothesis_results: dict[str, object] = {}
        for hypothesis in HYPOTHESES:
            folds = []
            train_end = initial_train_count
            fold_number = 1
            while train_end + validation_count <= len(timeline):
                if fold_number > MAX_FOLDS:
                    raise ValueError("walk-forward fold count exceeds bounded maximum")
                validation_end = train_end + validation_count
                start = timeline[train_end]
                end_exclusive = timeline[validation_end - 1] + timedelta(hours=1)
                book = simulate_shared_research_book(
                    rows,
                    specs={symbol: candidate(symbol) for symbol in SYMBOLS},
                    hypotheses={symbol: hypothesis for symbol in SYMBOLS},
                    assumptions={symbol: cost for symbol in SYMBOLS},
                    as_of=checked_at,
                    equity_calendars={symbol: timeline for symbol in SYMBOLS},
                    evaluation_start_utc=start,
                    evaluation_end_utc_exclusive=end_exclusive,
                )
                if (
                    book.get("broker_order_submission") != "DISABLED"
                    or book.get("live_trading") != "UNAVAILABLE"
                    or book.get("past_data_does_not_prove_strategy_edge") is not True
                ):
                    raise ValueError("walk-forward simulation escaped research-only contract")
                folds.append({
                    "fold": fold_number,
                    "train_context_core_hours": train_end,
                    "validation_core_hours": validation_count,
                    "validation_start_utc": start.isoformat(),
                    "validation_end_utc_exclusive": end_exclusive.isoformat(),
                    "net_pnl_if_hypothetically_liquidated_usd":
                        book["net_pnl_if_hypothetically_liquidated_usd"],
                    "sampled_event_max_drawdown_usd":
                        book["sampled_event_max_drawdown_usd"],
                    "synthetic_fill_count": len(book["synthetic_fills"]),
                    "persistent_peak_drawdown_entry_halt":
                        book["persistent_peak_drawdown_entry_halt"],
                    "historical_assets_sha256": book["historical_assets_sha256"],
                })
                train_end += step_count
                fold_number += 1
            if not folds:
                raise ValueError("walk-forward produced no validation fold")
            hypothesis_results[hypothesis.name] = {
                "folds": folds,
                "fold_count": len(folds),
                "strategy_selected_from_fold_results": False,
                "hyperparameter_tuning_from_fold_results": False,
            }
        scenarios[scenario_name] = {
            "assumptions": dict(raw_costs),
            "hypotheses": hypothesis_results,
        }

    fold_counts = {
        item["fold_count"]
        for scenario in scenarios.values()
        for item in scenario["hypotheses"].values()
    }
    if len(fold_counts) != 1:
        raise AssertionError("all scenarios and hypotheses must use identical fold clocks")

    return {
        "kind": "OFFLINE_EXPANDING_WALK_FORWARD_SIX_STOCK_RESEARCH",
        "symbols": list(SYMBOLS),
        "feed": "alpaca_equity_iex",
        "verified_core_hours_per_asset": len(timeline),
        "initial_train_context_core_hours": initial_train_count,
        "validation_core_hours_per_fold": validation_count,
        "step_core_hours": step_count,
        "fold_count": next(iter(fold_counts)),
        "three_fixed_friction_scenarios": scenarios,
        "all_hypotheses_predeclared": [h.name for h in HYPOTHESES],
        "strategy_selection_performed": False,
        "hyperparameter_optimization_performed": False,
        "historical_walk_forward_complete": True,
        "historical_walk_forward_is_not_prospective_validation": True,
        "prospective_observations_verified": 0,
        "automatic_strategy_promotion": "DISABLED",
        "credentials_accessed": "NONE",
        "network_requests": "NONE",
        "broker_order_submission": "DISABLED",
        "live_trading": "UNAVAILABLE",
    }


def _reload_phase48_verified_source(
    source_root: Path,
    *,
    baseline: Mapping[str, object],
    as_of: datetime,
) -> tuple[dict[str, tuple[ResearchBar, ...]], tuple[datetime, ...]]:
    """Re-read the source after Phase48 validation and bind it to that receipt."""
    manifest, manifest_raw = _read_object(
        source_root / "long_horizon_manifest.json",
        max_bytes=MAX_MANIFEST_BYTES,
    )
    if hashlib.sha256(manifest_raw).hexdigest() != baseline["source_manifest_sha256"]:
        raise ValueError("long-equity manifest changed after Phase48 validation")
    chunks = manifest.get("chunks")
    if not isinstance(chunks, list):
        raise ValueError("long-equity chunks missing during walk-forward reload")
    receipts = baseline.get("chunk_receipts")
    if not isinstance(receipts, list) or len(receipts) != len(chunks):
        raise ValueError("Phase48 chunk receipts do not match source")

    batches = []
    grid: list[datetime] = []
    last: datetime | None = None
    for index, (chunk, receipt) in enumerate(zip(chunks, receipts), 1):
        if not isinstance(chunk, Mapping) or not isinstance(receipt, Mapping):
            raise ValueError("invalid chunk metadata during walk-forward reload")
        folder = source_root / f"chunk-{index:03d}"
        report, raw = _read_object(
            folder / "offline_equity_research.json",
            max_bytes=MAX_REPORT_BYTES,
        )
        if hashlib.sha256(raw).hexdigest() != receipt.get("report_sha256"):
            raise ValueError("chunk report changed after Phase48 validation")
        sessions = report.get("exchange_calendar_session_plan", {}).get("sessions")
        sources = report.get("source_sha256")
        if not isinstance(sessions, list) or not isinstance(sources, list):
            raise ValueError("walk-forward source provenance missing")
        for session in sessions:
            opens = session.get("expected_core_bucket_opens_utc") if isinstance(session, Mapping) else None
            if not isinstance(opens, list):
                raise ValueError("walk-forward exchange grid missing")
            for raw_open in opens:
                opened = _stamp(raw_open)
                if last is not None and opened <= last:
                    raise ValueError("walk-forward exchange grid duplicated or regressed")
                grid.append(opened)
                last = opened
        for source in sources:
            if not isinstance(source, Mapping):
                raise ValueError("invalid source manifest row")
            name = source.get("filename")
            digest = source.get("sha256")
            if (
                not isinstance(name, str)
                or "/" in name
                or "\\" in name
                or not isinstance(digest, str)
            ):
                raise ValueError("unsafe source path in walk-forward reload")
            path = folder / name
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError("source archive changed after Phase48 validation")
            batches.append(read_historical_archive(path))

    timeline = tuple(grid)
    if (
        len(timeline) != baseline["verified_core_hours_per_asset"]
        or timeline[0].isoformat() != baseline["first_core_open_utc"]
        or timeline[-1].isoformat() != baseline["last_core_open_utc"]
    ):
        raise ValueError("walk-forward grid differs from Phase48 validation")
    datasets, _ = combine_historical_archives(
        tuple(batches),
        as_of=as_of.astimezone(timezone.utc),
        equity_calendars={symbol: timeline for symbol in SYMBOLS},
    )
    return datasets, timeline


def validate_long_equity_walk_forward(
    source_root: str | Path,
    *,
    as_of: datetime,
    initial_train_count: int = DEFAULT_INITIAL_TRAIN_CORE_HOURS,
    validation_count: int = DEFAULT_VALIDATION_CORE_HOURS,
    step_count: int = DEFAULT_STEP_CORE_HOURS,
) -> dict[str, object]:
    root = Path(source_root)
    baseline = validate_long_equity_history(root, as_of=as_of)
    datasets, timeline = _reload_phase48_verified_source(
        root,
        baseline=baseline,
        as_of=as_of,
    )
    result = expanding_equity_walk_forward(
        datasets,
        grid=timeline,
        as_of=as_of,
        initial_train_count=initial_train_count,
        validation_count=validation_count,
        step_count=step_count,
    )
    result["phase48_source_manifest_sha256"] = baseline["source_manifest_sha256"]
    result["phase48_three_way_validation_replayed_first"] = True
    return result

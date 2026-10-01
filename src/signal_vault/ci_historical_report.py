"""Offline post-download multi-asset historical analysis for an EXPLICIT manual CI run.

This module never reads Alpaca credentials, makes network calls, reclassifies
historical data as prospective evidence, promotes a strategy, or submits orders.
A successful manually requested crypto DATA GET can be followed in the SAME
GitHub Actions job by independent SHA/read-back and descriptive 3-scenario
cost-aware comparisons. The uploaded artifacts remain private and expire.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence

from .ci_historical_crypto import OUTPUT, resolve_manual_ci_configuration
from .multi_asset_historical import HistoricalDataBatch
from .multi_asset_simulation import (
    HYPOTHESES,
    HypothesisKind,
    ResearchHypothesis,
)
from .multi_asset_research_cli import run_offline_report
from .offline_multimarket_pipeline import read_historical_archive

ANALYSIS_FILENAME = "offline_research_analysis.json"
MAX_WINDOWS = 30
CRYPTO_BOOTSTRAP_HYPOTHESES = HYPOTHESES + (
    ResearchHypothesis(
        HypothesisKind.EMA_CONFIRM,
        "generic-ema12x26-confirm2-v2-predeclared",
    ),
)

# These are ILLUSTRATIVE SCENARIOS, not current provider prices, broker fees,
# forecasts or recommended trading choices. A separate fee/quote audit is
# mandatory before any decision involving actual execution.
SCENARIOS: Mapping[str, Mapping[str, str]] = {
    "illustrative_low_friction": {
        "taker_fee_bps": "15", "full_spread_bps": "2",
        "slippage_per_side_bps": "5",
    },
    "illustrative_base_friction": {
        "taker_fee_bps": "25", "full_spread_bps": "4",
        "slippage_per_side_bps": "10",
    },
    "illustrative_high_friction": {
        "taker_fee_bps": "40", "full_spread_bps": "12",
        "slippage_per_side_bps": "20",
    },
}


def _private_folder(folder: Path) -> Path:
    if folder.is_symlink() or not folder.is_dir() or folder.stat().st_mode & 0o077:
        raise ValueError("history directory must be existing nonsymlink 0700")
    return folder


def _safe_write_once(target: Path, payload: bytes) -> None:
    if target.exists() or target.is_symlink():
        raise ValueError("analysis output path already exists; no overwriting old results")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(target, flags, 0o600)
    with os.fdopen(fd, "wb") as writer:
        os.fchmod(writer.fileno(), 0o600)
        writer.write(payload)
        writer.flush()
        os.fsync(writer.fileno())


def audit_requested_archives(
    folder: Path, *, plan: Mapping[str, object],
) -> tuple[Path, ...]:
    """Fail closed if partial, duplicate or stale history is mixed into a run.

    Important: Alpaca's returned multi-symbol page limit is TOTAL, and each
    downloaded window must include every separately requested instrument.
    Read-back validates the immutable SHA-named file, manifest, chronology,
    both (or more) symbols and historical-only provenance before comparison.
    """
    root = _private_folder(folder)
    if (not isinstance(plan, Mapping)
            or plan.get("kind") != "OFFLINE_PREDECLARED_HISTORICAL_GET_PLAN_NO_NETWORK"
            or plan.get("market") != "crypto"
            or plan.get("broker_order_submission") != "DISABLED"):
        raise ValueError("invalid manual historical plan")
    request_symbols = tuple(sorted(plan.get("symbols", ())))
    windows = plan.get("windows")
    if (not request_symbols or len(set(request_symbols)) != len(request_symbols)
            or not isinstance(windows, list)
            or not 1 <= len(windows) <= MAX_WINDOWS
            or plan.get("window_count") != len(windows)):
        raise ValueError("incomplete bounded historical plan")
    paths = tuple(sorted(root.glob("historical-crypto-*.json")))
    if len(paths) != len(windows):
        raise ValueError("missing/extra history archives; no partial success claims")
    if (any(item.is_symlink() for item in paths)
            or any(entry.is_symlink() for entry in root.iterdir())):
        raise ValueError("symlinks disallowed in history analysis folder")
    window_map = {
        (win["start_utc"], win["end_utc"]): index
        for index, win in enumerate(windows)
    }
    if len(window_map) != len(windows):
        raise ValueError("duplicated planned historical window")
    reviewed: dict[int, Path] = {}
    for path in paths:
        batch: HistoricalDataBatch = read_historical_archive(path)
        if batch.asset_class != "crypto" or batch.symbols != request_symbols:
            raise ValueError("wrong instrument group in downloaded archive")
        if batch.feed != "alpaca_crypto_us" or batch.adjustment != "not_applicable":
            raise ValueError("wrong historical provider/feed")
        key = (batch.start_utc, batch.end_utc)
        if key not in window_map or window_map[key] in reviewed:
            raise ValueError("archived interval differs from requested plan")
        if any(not rows for rows in batch.bars.values()):
            raise ValueError("missing requested historical instrument")
        reviewed[window_map[key]] = path
    if len(reviewed) != len(windows):
        raise ValueError("missing one or more requested historical windows")
    return tuple(reviewed[i] for i in range(len(windows)))


def _comparison_summary(raw: Mapping[str, object]) -> dict[str, object]:
    if (raw.get("kind")
            != "OFFLINE_MULTIASSET_COMPARATIVE_HISTORICAL_RESEARCH_NOT_TRADING"
            or raw.get("broker_order_submission") != "DISABLED"
            or raw.get("network_requests") != "NONE"
            or raw.get("credential_access") != "NONE"
            or raw.get("research_only_historical") is not True):
        raise ValueError("invalid offline comparative report")
    books = raw["all_predeclared_shared_bankroll_research_books"]
    return {
        "asset_quality_reviews": raw["per_symbol_quality_reviews"],
        "historical_archive_count": raw["historical_archive_count"],
        "predeclared_hypotheses": raw["predeclared_hypotheses"],
        "per_asset_disjoint_chronological_folds":
            raw["per_asset_chronological_folds"],
        "one_SHARED_100_usd_portfolio_by_fixed_hypothesis": {
            version: {
                "initial_bankroll_usd": book["initial_bankroll_usd"],
                "cash_usd": book["cash_usd"],
                "net_marked_pnl_usd": book["net_marked_pnl_usd"],
                "net_pnl_if_hypothetically_liquidated_usd":
                    book["net_pnl_if_hypothetically_liquidated_usd"],
                "sampled_event_max_drawdown_usd":
                    book["sampled_event_max_drawdown_usd"],
                "research_risk_gate_semantics_version":
                    book["research_risk_gate_semantics_version"],
                "utc_daily_entry_pause_dates": book["utc_daily_entry_pause_dates"],
                "persistent_peak_drawdown_entry_halt":
                    book["persistent_peak_drawdown_entry_halt"],
                "estimated_fee_total_usd": book["estimated_fee_total_usd"],
                "synthetic_fill_count": len(book["synthetic_fills"]),
                "rejected_synthetic_fill_count": len(book["rejections"]),
                "historical_assets_sha256": book["historical_assets_sha256"],
                "provider_paper_positions_queried": False,
                "broker_order_submission": "DISABLED",
            }
            for version, book in books.items()
        },
        "strategy_chosen_from_validation_or_test": False,
        "simulation_accounting_version":
            "v2_utc_daily_reset_plus_persistent_peak_drawdown_halt",
    }


def analyze_manual_history(
    *,
    folder: Path,
    plan: Mapping[str, object],
    scenario_models: Mapping[str, Mapping[str, str]] = SCENARIOS,
    report_reader=run_offline_report,
    archive_auditor=audit_requested_archives,
) -> dict[str, object]:
    """Independently reconstruct all expected windows and stress assumed costs.

    Produces ONE deterministic archived report plus its own SHA. Never stores
    provider keys, never uses test-set winners to select a strategy, and does
    not edit the source historical archive files.
    """
    root = _private_folder(folder)
    archives = archive_auditor(root, plan=plan)
    request_symbols = tuple(sorted(plan["symbols"]))
    if set(scenario_models) != set(SCENARIOS):
        raise ValueError("all three fixed stress labels are required")
    scenarios = {}
    for label in SCENARIOS:
        params = scenario_models[label]
        if (not isinstance(params, Mapping) or
                set(params) != {
                    "taker_fee_bps", "full_spread_bps",
                    "slippage_per_side_bps"}):
            raise ValueError("invalid declared cost scenario")
        for value in params.values():
            val = Decimal(value)
            if not val.is_finite() or val < 0 or val > 1000:
                raise ValueError("invalid historical cost estimate")
        # Preserve the model alongside the report; never pretend the estimate
        # equals an actual execution, current spread or broker fee statement.
        costs = {
            symbol: dict(params) for symbol in request_symbols
        }
        cost_path = root / ("cost_assumptions-" + label + ".json")
        data = (json.dumps(costs, sort_keys=True, separators=(",", ":"))
                + "\n").encode("utf-8")
        _safe_write_once(cost_path, data)
        if report_reader is run_offline_report:
            raw = report_reader(
                archives,
                cost_config=cost_path,
                hypotheses=CRYPTO_BOOTSTRAP_HYPOTHESES,
            )
        else:
            raw = report_reader(archives, cost_config=cost_path)
        scenarios[label] = {
            "assumptions_per_instrument": costs,
            "estimated_not_observed_fees_and_spreads": True,
            "offline_report": _comparison_summary(raw),
        }
    audit = tuple({
        "filename": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    } for path in archives)
    record = {
        "kind": "HISTORICAL_MULTIASSET_SHA_BOUND_THREE_COST_SCENARIOS_NO_ORDERS",
        "schema_version": 1,
        "market": plan["market"],
        "symbols": list(request_symbols),
        "predeclared_request_windows": list(plan["windows"]),
        "historical_archive_audit": list(audit),
        "completed_historical_windows": len(audit),
        "scenarios": scenarios,
        "data_is_historical_not_new_prospective_observations": True,
        "independent_forward_strategy_edge_established": False,
        "simulation_accounting_version":
            "v2_utc_daily_reset_plus_persistent_peak_drawdown_halt",
        "previous_v1_historical_outputs_are_not_directly_comparable": True,
        "candidate_selection_from_untouched_test": False,
        "strategy_promoted": False,
        "network_requests_during_analysis": "NONE",
        "credential_access_during_analysis": "NONE",
        "broker_order_submission": "DISABLED",
        "live_trading": "UNAVAILABLE",
    }
    payload = (json.dumps(record, sort_keys=True, indent=2) + "\n").encode("utf-8")
    _safe_write_once(root / ANALYSIS_FILENAME, payload)
    return {
        "kind": "POST_HISTORY_ANALYSIS_COMPLETED_NO_ORDERS",
        "status": "COMPLETE_HISTORICAL_DATA_AND_THREE_COST_SCENARIOS",
        "symbols": list(request_symbols),
        "historical_archive_count": len(audit),
        "cost_scenarios": list(scenarios),
        "research_report_basename": ANALYSIS_FILENAME,
        "research_report_sha256": hashlib.sha256(payload).hexdigest(),
        "network_requests_during_analysis": "NONE",
        "credential_access_during_analysis": "NONE",
        "proven_future_return": False,
        "strategy_promoted": False,
        "broker_order_submission": "DISABLED",
    }


def main() -> int:
    """Actions only: abort on invalid context; print only error CLASS, not keys."""
    try:
        plan = resolve_manual_ci_configuration(env=os.environ)["plan"]
        result = analyze_manual_history(folder=OUTPUT, plan=plan)
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "kind": "POST_HISTORY_OFFLINE_ANALYSIS",
            "status": "BLOCKED_PRESERVE_ALL_DOWNLOADED_ARCHIVES",
            "failure_class": type(exc).__name__,
            "no_secret_values_in_output": True,
            "broker_order_submission": "DISABLED",
            "network_requests_during_analysis": "NONE",
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Single preregistered research-only v0.3 development experiment.

Strictly loads only the previously examined, locally SHA-verified 1,843-bar
PRE-GAP dataset. The reserved post-gap source is never referenced or read.
No API credentials, market-data network calls or order executor exist here.
See docs/RESEARCH_V03.md (written before the first v0.3 owner backtest).
"""
from __future__ import annotations

import json
from decimal import Decimal
from hashlib import sha256
from statistics import median

from .backtest import CostAssumptions, BacktestResult, chronological_research_folds, simulate
from .market_data import load_csv
from .research_v02 import (
    DEVELOPMENT_CSV, DEVELOPMENT_SHA256, DEVELOPMENT_END, DEVELOPMENT_ROWS, V01, _summary,
)
from .strategy import StrategyConfig

V03 = StrategyConfig(
    fast_hours=12,
    slow_hours=26,
    strategy_version="btc-hourly-ema-cross-24h-momentum-v0.3-RESEARCH-ONLY",
    entry_confirmation_bars=1,
    entry_minimum_prior_24h_return_bps=Decimal("50"),
)


def development_gate(candidate: BacktestResult, baseline: BacktestResult) -> dict:
    """Apply the fixed five criteria in docs/RESEARCH_V03.md, never optimize."""
    if candidate.assumptions != baseline.assumptions:
        raise ValueError("cannot gate strategies under different cost assumptions")
    reasons = []
    if candidate.net_pnl_usd <= 0:
        reasons.append("after-cost aggregate development P&L is not positive")
    if candidate.net_pnl_usd <= baseline.net_pnl_usd:
        reasons.append("after-cost P&L does not outperform v0.1")
    if candidate.net_pnl_usd <= candidate.passive_same_allocation_net_pnl_usd:
        reasons.append("after-cost P&L does not outperform same-allocation passive BTC")
    if candidate.max_drawdown_usd > baseline.max_drawdown_usd:
        reasons.append("development drawdown exceeds v0.1")
    if sum(fill.side == "sell" for fill in candidate.fills) < 4:
        reasons.append("fewer than four completed sell exits")
    if candidate.rejected:
        reasons.append("risk or order-size actions were rejected")
    return {
        "kind": "OFFLINE_V03_DEVELOPMENT_GATE_NOT_BROKER_AUTHORIZATION",
        "passed": not reasons,
        "reasons": reasons,
        "eligible_for_reserved_holdout_review": not reasons,
        "broker_order_submission": "DISABLED",
    }


def _fold_summary(bars, strategy: StrategyConfig) -> dict:
    folds = chronological_research_folds(
        bars, as_of=DEVELOPMENT_END, strategy=strategy, evaluation_hours=168)
    if not folds:
        raise ValueError("no development folds")
    pnl = [fold.result.net_pnl_usd for fold in folds]
    return {
        "fold_duration_hours": 168,
        "fold_count": len(folds),
        "aggregate_fold_net_pnl_usd": str(sum(pnl, Decimal("0"))),
        "median_fold_net_pnl_usd": str(median(pnl)),
        "positive_fold_count": sum(p > 0 for p in pnl),
        "passive_outperformance_fold_count": sum(
            fold.result.net_pnl_usd > fold.result.passive_same_allocation_net_pnl_usd
            for fold in folds),
        "total_fold_fills": sum(len(fold.result.fills) for fold in folds),
        "note": "Overlapping indicator warmup; disjoint trading windows each reset $100. Descriptive development folds only.",
    }


def main() -> int:
    actual = sha256(DEVELOPMENT_CSV.read_bytes()).hexdigest()
    if actual != DEVELOPMENT_SHA256:
        raise ValueError("predeclared pre-gap development dataset SHA-256 mismatch")
    bars = load_csv(DEVELOPMENT_CSV, as_of=DEVELOPMENT_END, min_count=DEVELOPMENT_ROWS)
    if (len(bars) != DEVELOPMENT_ROWS
            or bars[0].start.isoformat() != "2025-12-25T22:00:00+00:00"
            or bars[-1].close_time != DEVELOPMENT_END):
        raise ValueError("development dataset rows or UTC boundaries differ from preregistration")
    free = CostAssumptions(taker_fee_rate=Decimal("0"), slippage_rate=Decimal("0"))
    v01 = simulate(bars, as_of=DEVELOPMENT_END, strategy=V01)
    v03 = simulate(bars, as_of=DEVELOPMENT_END, strategy=V03)
    v01_free = simulate(bars, as_of=DEVELOPMENT_END, strategy=V01, costs=free)
    v03_free = simulate(bars, as_of=DEVELOPMENT_END, strategy=V03, costs=free)
    gate = development_gate(v03, v01)
    if v03_free.net_pnl_usd <= 0:
        gate["reasons"].insert(1, "zero-cost aggregate development P&L is not positive")
        gate["passed"] = False
        gate["eligible_for_reserved_holdout_review"] = False
    report = {
        "kind": "OFFLINE_PREDECLARED_V03_DEVELOPMENT_ONLY_NOT_PAPER_APPROVAL",
        "dataset_sha256": actual,
        "data_scope": "SHA-LOCKED PRE-GAP ONLY; NO POST-GAP DATA OPENED",
        "hypothesis": "v0.1 BUY only if last CLOSED price gained >=50 bps versus 24h earlier CLOSED price; immediate SELL unchanged",
        "threshold_preselected_from_exploratory_development_data": True,
        "baseline_v01": _summary(v01),
        "candidate_v03": _summary(v03),
        "baseline_v01_no_costs": _summary(v01_free),
        "candidate_v03_no_costs": _summary(v03_free),
        "baseline_v01_development_folds": _fold_summary(bars, V01),
        "candidate_v03_development_folds": _fold_summary(bars, V03),
        "predeclared_development_gate": gate,
        "paper_order_submission": "DISABLED",
        "warning": "Passing a development gate only permits consideration of ONE independent evaluation after review. It never authorizes paper/live orders.",
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

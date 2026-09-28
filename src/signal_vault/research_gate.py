"""Predeclared research promotion gate for strategy candidates.

This gate is intentionally conservative and *not* a profitability guarantee.
It prevents a strategy from reaching provider-paper testing merely because one
backtest window looks good. Thresholds are versioned engineering policy and
must not be tuned on the final holdout interval.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from statistics import median
from typing import Sequence

from .backtest import ResearchFold


@dataclass(frozen=True)
class ResearchGatePolicy:
    policy_version: str = "btc-research-gate-v0.1"
    minimum_folds: int = 8
    minimum_fills: int = 10
    minimum_positive_fold_fraction: Decimal = Decimal("0.50")
    minimum_passive_outperformance_fraction: Decimal = Decimal("0.50")
    maximum_fold_drawdown_usd: Decimal = Decimal("10")

    def __post_init__(self) -> None:
        if not self.policy_version.strip() or self.minimum_folds < 2 or self.minimum_fills < 1:
            raise ValueError("invalid research gate policy")
        for value in (self.minimum_positive_fold_fraction,
                      self.minimum_passive_outperformance_fraction):
            if not isinstance(value, Decimal) or not value.is_finite() or not 0 <= value <= 1:
                raise ValueError("invalid research gate fraction")
        if (not isinstance(self.maximum_fold_drawdown_usd, Decimal) or
                not self.maximum_fold_drawdown_usd.is_finite() or
                self.maximum_fold_drawdown_usd <= 0):
            raise ValueError("invalid drawdown gate")


@dataclass(frozen=True)
class ResearchGateAssessment:
    policy_version: str
    passed: bool
    reasons: tuple[str, ...]
    fold_count: int
    fill_count: int
    positive_fold_count: int
    passive_outperformance_fold_count: int
    aggregate_net_pnl_usd: Decimal
    median_fold_net_pnl_usd: Decimal
    worst_fold_drawdown_usd: Decimal

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "OFFLINE_RESEARCH_GATE_NOT_LIVE_AUTHORIZATION",
            "policy_version": self.policy_version,
            "passed": self.passed,
            "reasons": list(self.reasons),
            "fold_count": self.fold_count,
            "fill_count": self.fill_count,
            "positive_fold_count": self.positive_fold_count,
            "passive_outperformance_fold_count": self.passive_outperformance_fold_count,
            "aggregate_net_pnl_usd": str(self.aggregate_net_pnl_usd),
            "median_fold_net_pnl_usd": str(self.median_fold_net_pnl_usd),
            "worst_fold_drawdown_usd": str(self.worst_fold_drawdown_usd),
            "warning": "Passing this gate is only permission for further paper research, not evidence of future profit.",
        }


def assess_research_folds(folds: Sequence[ResearchFold],
                          policy: ResearchGatePolicy | None = None) -> ResearchGateAssessment:
    cfg = policy or ResearchGatePolicy()
    results = tuple(f.result for f in folds)
    fold_count = len(results)
    fills = sum(len(r.fills) for r in results)
    positives = sum(1 for r in results if r.net_pnl_usd > 0)
    outperform = sum(1 for r in results
                     if r.net_pnl_usd > r.passive_same_allocation_net_pnl_usd)
    aggregate = sum((r.net_pnl_usd for r in results), Decimal("0"))
    median_pnl = Decimal("0") if not results else Decimal(str(median([r.net_pnl_usd for r in results])))
    worst_dd = max((r.max_drawdown_usd for r in results), default=Decimal("0"))
    reasons: list[str] = []
    if fold_count < cfg.minimum_folds:
        reasons.append("insufficient disjoint evaluation folds")
    if fills < cfg.minimum_fills:
        reasons.append("insufficient executed research fills")
    if aggregate <= 0:
        reasons.append("aggregate after-cost research P&L is not positive")
    if median_pnl <= 0:
        reasons.append("median fold after-cost P&L is not positive")
    if fold_count:
        positive_fraction = Decimal(positives) / Decimal(fold_count)
        outperform_fraction = Decimal(outperform) / Decimal(fold_count)
        if positive_fraction < cfg.minimum_positive_fold_fraction:
            reasons.append("too few positive evaluation folds")
        if outperform_fraction < cfg.minimum_passive_outperformance_fraction:
            reasons.append("too few folds outperform same-allocation passive BTC comparator")
    else:
        reasons.extend(("too few positive evaluation folds",
                        "too few folds outperform same-allocation passive BTC comparator"))
    if worst_dd > cfg.maximum_fold_drawdown_usd:
        reasons.append("research drawdown exceeds policy limit")
    return ResearchGateAssessment(cfg.policy_version, not reasons, tuple(reasons), fold_count,
                                  fills, positives, outperform, aggregate, median_pnl, worst_dd)

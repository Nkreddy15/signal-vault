"""Fixed chronological research protocol with a sealed final holdout window.

The protocol is a *paper-research gate*, not live authorization. Strategy and
cost assumptions must be declared before examining the final holdout result.
If the strategy is changed after seeing the holdout, use a newly captured or
future holdout period rather than pretending the old period is still unseen.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from .backtest import (BacktestResult, CostAssumptions, chronological_research_folds,
                       simulate)
from .market_data import Bar, validate_bars
from .research_gate import ResearchGateAssessment, ResearchGatePolicy, assess_research_folds
from .strategy import StrategyConfig


@dataclass(frozen=True)
class ResearchProtocolConfig:
    minimum_total_hours: int = 24 * 90
    final_holdout_hours: int = 24 * 30
    evaluation_fold_hours: int = 24 * 7
    minimum_holdout_fills: int = 2
    protocol_version: str = "btc-fixed-chronological-v0.1"

    def __post_init__(self) -> None:
        if (self.minimum_total_hours < 24 * 60 or self.final_holdout_hours < 24 * 7 or
                self.evaluation_fold_hours < 24 or self.minimum_holdout_fills < 1 or
                self.final_holdout_hours >= self.minimum_total_hours or
                not self.protocol_version.strip()):
            raise ValueError("invalid research protocol")


@dataclass(frozen=True)
class ResearchProtocolReport:
    protocol_version: str
    strategy_version: str
    dataset_sha256: str
    development_end_utc: str
    final_holdout_start_utc: str
    final_holdout_end_utc: str
    pre_holdout_gate: ResearchGateAssessment
    final_holdout: BacktestResult
    eligible_for_provider_paper_shadow: bool
    holdout_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "OFFLINE_FIXED_RESEARCH_PROTOCOL_NOT_LIVE_AUTHORIZATION",
            "protocol_version": self.protocol_version,
            "strategy_version": self.strategy_version,
            "dataset_sha256": self.dataset_sha256,
            "development_end_utc": self.development_end_utc,
            "final_holdout_start_utc": self.final_holdout_start_utc,
            "final_holdout_end_utc": self.final_holdout_end_utc,
            "pre_holdout_gate": self.pre_holdout_gate.to_dict(),
            "final_holdout": self.final_holdout.to_dict(),
            "eligible_for_provider_paper_shadow": self.eligible_for_provider_paper_shadow,
            "holdout_reasons": list(self.holdout_reasons),
            "warning": "Eligibility only permits further provider-paper testing; it does not predict live profit.",
        }


def run_research_protocol(bars: Sequence[Bar], *, dataset_sha256: str,
                          strategy: StrategyConfig | None = None,
                          costs: CostAssumptions | None = None,
                          gate_policy: ResearchGatePolicy | None = None,
                          protocol: ResearchProtocolConfig | None = None) -> ResearchProtocolReport:
    cfg = strategy or StrategyConfig()
    pcfg = protocol or ResearchProtocolConfig()
    if len(dataset_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in dataset_sha256.lower()):
        raise ValueError("valid SHA-256 dataset fingerprint required")
    sequence = validate_bars(bars, as_of=bars[-1].close_time if bars else None,
                             min_count=pcfg.minimum_total_hours)
    holdout_start = len(sequence) - pcfg.final_holdout_hours
    warmup = cfg.slow_hours + 2
    if holdout_start <= warmup + pcfg.evaluation_fold_hours:
        raise ValueError("insufficient pre-holdout research history")
    development = sequence[:holdout_start]
    folds = chronological_research_folds(
        development, as_of=development[-1].close_time, strategy=cfg,
        evaluation_hours=pcfg.evaluation_fold_hours, costs=costs)
    gate = assess_research_folds(folds, gate_policy)
    holdout_view = sequence[holdout_start - warmup:]
    final = simulate(holdout_view, as_of=sequence[-1].close_time,
                     strategy=cfg, costs=costs)
    reasons: list[str] = []
    if final.net_pnl_usd <= 0:
        reasons.append("final holdout after-cost P&L is not positive")
    if final.net_pnl_usd <= final.passive_same_allocation_net_pnl_usd:
        reasons.append("final holdout does not outperform same-allocation passive BTC comparator")
    if final.max_drawdown_usd > Decimal("10"):
        reasons.append("final holdout drawdown exceeds logical-account review threshold")
    if len(final.fills) < pcfg.minimum_holdout_fills:
        reasons.append("final holdout has too few research fills")
    eligible = gate.passed and not reasons
    return ResearchProtocolReport(
        pcfg.protocol_version, cfg.strategy_version, dataset_sha256.lower(),
        development[-1].close_time.isoformat(), sequence[holdout_start].start.isoformat(),
        sequence[-1].close_time.isoformat(), gate, final, eligible, tuple(reasons))

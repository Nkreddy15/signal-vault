"""Chronological walk-forward research for the optional ML BUY veto layer.

Every evaluation fold trains only on data that closed before the evaluation
window. The deterministic EMA baseline and EMA+ML confirmation variant are run
on the same later candles with identical costs and $100 logical capital.
Nothing in this module grants provider-paper or live execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from statistics import median
from typing import Sequence
import json

from .backtest import BacktestResult, CostAssumptions, simulate
from .market_data import Bar, validate_bars
from .ml_training import MlTrainingConfig, train_logistic_confirmation
from .risk import RiskLimits
from .strategy import StrategyConfig


def bars_fingerprint(bars: Sequence[Bar]) -> str:
    rows = [
        [b.start.isoformat(), str(b.open), str(b.high), str(b.low), str(b.close), str(b.volume),
         b.source, b.timeframe_seconds, b.symbol]
        for b in bars
    ]
    return sha256(json.dumps(rows, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


@dataclass(frozen=True)
class MlWalkForwardConfig:
    minimum_training_hours: int = 24 * 45
    evaluation_hours: int = 24 * 7
    minimum_folds: int = 4

    def __post_init__(self) -> None:
        if self.minimum_training_hours < 24 * 30:
            raise ValueError("ML walk-forward requires at least 30 days of prior training data")
        if self.evaluation_hours < 24 or self.minimum_folds < 2:
            raise ValueError("invalid ML walk-forward configuration")


@dataclass(frozen=True)
class MlWalkForwardFold:
    training_end_utc: str
    evaluation_start_utc: str
    evaluation_end_utc: str
    training_dataset_sha256: str
    artifact_sha256: str
    baseline: BacktestResult
    confirmed: BacktestResult

    @property
    def pnl_improvement_usd(self) -> Decimal:
        return self.confirmed.net_pnl_usd - self.baseline.net_pnl_usd


@dataclass(frozen=True)
class MlWalkForwardReport:
    folds: tuple[MlWalkForwardFold, ...]
    aggregate_baseline_pnl_usd: Decimal
    aggregate_confirmed_pnl_usd: Decimal
    median_fold_improvement_usd: Decimal
    confirmed_better_fold_fraction: Decimal
    worst_baseline_drawdown_usd: Decimal
    worst_confirmed_drawdown_usd: Decimal
    research_candidate_pass: bool
    reasons: tuple[str, ...]

    @property
    def kind(self) -> str:
        return "OFFLINE_ML_WALK_FORWARD_RESEARCH_NOT_PROVIDER_PAPER_OR_LIVE_AUTHORIZATION"


def walk_forward_ml_confirmation(
    bars: Sequence[Bar], *, as_of: datetime,
    config: MlWalkForwardConfig | None = None,
    training: MlTrainingConfig | None = None,
    strategy: StrategyConfig | None = None,
    costs: CostAssumptions | None = None,
    limits: RiskLimits | None = None,
) -> MlWalkForwardReport:
    cfg = config or MlWalkForwardConfig()
    strat = strategy or StrategyConfig()
    warmup = strat.slow_hours + 2
    # Need enough future data for at least the requested number of untouched evaluations.
    required = cfg.minimum_training_hours + cfg.evaluation_hours * cfg.minimum_folds
    seq = validate_bars(bars, as_of=as_of, min_count=required)
    folds: list[MlWalkForwardFold] = []
    start = cfg.minimum_training_hours
    while start + cfg.evaluation_hours <= len(seq):
        training_bars = seq[:start]
        train_sha = bars_fingerprint(training_bars)
        artifact = train_logistic_confirmation(training_bars, dataset_sha256=train_sha, config=training)
        if datetime.fromisoformat(artifact.trained_until_utc) > seq[start].start:
            raise ValueError("ML training cutoff leaked into evaluation interval")
        stop = start + cfg.evaluation_hours
        eval_view = seq[start - warmup:stop]
        baseline = simulate(eval_view, as_of=eval_view[-1].close_time,
                            strategy=strat, costs=costs, limits=limits)
        confirmed = simulate(eval_view, as_of=eval_view[-1].close_time,
                             strategy=strat, costs=costs, limits=limits,
                             confirmation_artifact=artifact)
        folds.append(MlWalkForwardFold(
            training_end_utc=training_bars[-1].close_time.isoformat(),
            evaluation_start_utc=seq[start].start.isoformat(),
            evaluation_end_utc=seq[stop - 1].close_time.isoformat(),
            training_dataset_sha256=train_sha,
            artifact_sha256=artifact.fingerprint(), baseline=baseline, confirmed=confirmed,
        ))
        start = stop
    if len(folds) < cfg.minimum_folds:
        raise ValueError("insufficient complete ML evaluation folds")

    base_total = sum((f.baseline.net_pnl_usd for f in folds), Decimal("0"))
    ml_total = sum((f.confirmed.net_pnl_usd for f in folds), Decimal("0"))
    improvements = [f.pnl_improvement_usd for f in folds]
    better = sum(x > 0 for x in improvements)
    fraction = Decimal(better) / Decimal(len(folds))
    worst_base = max(f.baseline.max_drawdown_usd for f in folds)
    worst_ml = max(f.confirmed.max_drawdown_usd for f in folds)
    reasons: list[str] = []
    # Predeclared conservative screen for *further research only*. We require
    # improvement in aggregate and median without increasing worst drawdown.
    if ml_total <= base_total:
        reasons.append("ML confirmation did not improve aggregate after-cost P&L")
    med = median(improvements)
    if med <= 0:
        reasons.append("ML confirmation did not improve the median evaluation fold")
    if fraction < Decimal("0.5"):
        reasons.append("ML confirmation improved fewer than half of evaluation folds")
    if worst_ml > worst_base:
        reasons.append("ML confirmation increased worst observed fold drawdown")
    return MlWalkForwardReport(tuple(folds), base_total, ml_total, med, fraction,
                               worst_base, worst_ml, not reasons, tuple(reasons))

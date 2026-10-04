"""Independent-model consensus builder for Phase 162 Signal Vault.

Market-specific research engines emit ModelSignal records.  This module combines
multiple independent model/strategy opinions into one normalized Opportunity
for the common cross-market allocator.

It intentionally rejects the architecture where one narrow condition controls
the portfolio.  By default, at least two independent source models must support
the same direction and their confidence-weighted vote must clear a consensus
threshold.

No network clients, broker imports, credentials, order submission, or live mode
exist here.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable

from .opportunity_engine import Direction, Market, Opportunity


def _utc(value: datetime, *, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _dec(value: Decimal, *, name: str) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal")
    return value


def _allowed_directions(market: Market) -> frozenset[Direction]:
    if market in {Market.CRYPTO, Market.US_EQUITY}:
        return frozenset({Direction.LONG, Direction.SHORT})
    if market is Market.EVENT_CONTRACT:
        return frozenset({Direction.YES, Direction.NO})
    raise ValueError("unsupported normalized market")


@dataclass(frozen=True)
class ModelSignal:
    market: Market
    instrument: str
    source_model: str
    strategy_family: str
    direction: Direction
    generated_utc: datetime
    valid_until_utc: datetime
    horizon_seconds: int
    expected_gross_return: Decimal
    estimated_round_trip_cost_return: Decimal
    confidence: Decimal
    max_loss_return: Decimal
    evidence_id: str
    correlation_group: str
    paper_executable: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.market, Market):
            raise ValueError("normalized market required")
        if self.direction not in _allowed_directions(self.market):
            raise ValueError("direction is incompatible with market lane")
        if (
            not isinstance(self.instrument, str)
            or not self.instrument.strip()
            or len(self.instrument) > 80
        ):
            raise ValueError("invalid instrument")
        for value, label, max_len in (
            (self.source_model, "source model", 160),
            (self.strategy_family, "strategy family", 120),
            (self.evidence_id, "evidence id", 256),
            (self.correlation_group, "correlation group", 80),
        ):
            if not isinstance(value, str) or not value.strip() or len(value) > max_len:
                raise ValueError(f"invalid {label}")
        generated = _utc(self.generated_utc, name="generated_utc")
        valid_until = _utc(self.valid_until_utc, name="valid_until_utc")
        if valid_until <= generated:
            raise ValueError("signal validity must extend past generation")
        if type(self.horizon_seconds) is not int or self.horizon_seconds <= 0:
            raise ValueError("positive signal horizon required")
        gross = _dec(self.expected_gross_return, name="expected gross return")
        costs = _dec(
            self.estimated_round_trip_cost_return,
            name="estimated round-trip cost",
        )
        confidence = _dec(self.confidence, name="confidence")
        max_loss = _dec(self.max_loss_return, name="max loss")
        if gross < Decimal("-1") or gross > Decimal("10"):
            raise ValueError("gross return estimate outside research bounds")
        if costs < 0 or costs > Decimal("1"):
            raise ValueError("cost estimate outside research bounds")
        if not Decimal("0") <= confidence <= Decimal("1"):
            raise ValueError("confidence outside [0,1]")
        if not Decimal("0") < max_loss <= Decimal("1"):
            raise ValueError("max loss return outside (0,1]")
        if type(self.paper_executable) is not bool:
            raise ValueError("paper executable flag must be boolean")

    @property
    def expected_net_return(self) -> Decimal:
        return self.expected_gross_return - self.estimated_round_trip_cost_return


@dataclass(frozen=True)
class EnsembleBuildResult:
    opportunities: tuple[Opportunity, ...]
    rejected_groups: tuple[dict[str, object], ...]
    active_signal_count: int
    expired_signal_count: int


def _opposite(direction: Direction) -> Direction:
    if direction is Direction.LONG:
        return Direction.SHORT
    if direction is Direction.SHORT:
        return Direction.LONG
    if direction is Direction.YES:
        return Direction.NO
    if direction is Direction.NO:
        return Direction.YES
    raise ValueError("unknown direction")


def build_ensemble_opportunities(
    signals: Iterable[ModelSignal],
    *,
    as_of: datetime,
    min_independent_models: int = 2,
    min_consensus: Decimal = Decimal("0.60"),
    min_expected_net_return: Decimal = Decimal("0.001"),
) -> EnsembleBuildResult:
    """Build after-cost consensus opportunities from many independent opinions.

    Signals are grouped by market + instrument + horizon.  A source model may
    contribute exactly one opinion to a group.  Opposing votes reduce consensus.
    The winning direction must have enough independent positive-net models.

    Thresholds here are structural gates only; they are not trading advice and
    do not bypass the downstream shared allocator/risk governor.
    """
    now = _utc(as_of, name="as_of")
    if type(min_independent_models) is not int or not 1 <= min_independent_models <= 50:
        raise ValueError("invalid independent model minimum")
    consensus_floor = _dec(min_consensus, name="minimum consensus")
    edge_floor = _dec(min_expected_net_return, name="minimum net return")
    if not Decimal("0.5") <= consensus_floor <= Decimal("1"):
        raise ValueError("minimum consensus must be within [0.5,1]")
    if edge_floor < 0 or edge_floor > Decimal("1"):
        raise ValueError("minimum net return outside research bounds")

    active: list[ModelSignal] = []
    expired = 0
    seen_evidence: set[str] = set()
    for signal in signals:
        if not isinstance(signal, ModelSignal):
            raise TypeError("ModelSignal inputs required")
        if signal.evidence_id in seen_evidence:
            raise ValueError("duplicate signal evidence id")
        seen_evidence.add(signal.evidence_id)
        generated = _utc(signal.generated_utc, name="generated_utc")
        valid_until = _utc(signal.valid_until_utc, name="valid_until_utc")
        if generated > now:
            raise ValueError("future signal evidence is forbidden")
        if valid_until <= now:
            expired += 1
            continue
        active.append(signal)

    grouped: dict[tuple[Market, str, int], list[ModelSignal]] = {}
    for signal in active:
        grouped.setdefault(
            (signal.market, signal.instrument, signal.horizon_seconds),
            [],
        ).append(signal)

    opportunities: list[Opportunity] = []
    rejected: list[dict[str, object]] = []

    for (market, instrument, horizon), members in sorted(
        grouped.items(),
        key=lambda item: (
            item[0][0].value,
            item[0][1],
            item[0][2],
        ),
    ):
        by_model: dict[str, ModelSignal] = {}
        for member in members:
            if member.source_model in by_model:
                rejected.append({
                    "market": market.value,
                    "instrument": instrument,
                    "horizon_seconds": horizon,
                    "reason": "DUPLICATE_MODEL_OPINION",
                    "source_model": member.source_model,
                })
                by_model = {}
                break
            by_model[member.source_model] = member
        if not by_model:
            continue

        vote_weight = {
            direction: Decimal("0")
            for direction in _allowed_directions(market)
        }
        for member in by_model.values():
            vote_weight[member.direction] += member.confidence

        winner = max(
            vote_weight,
            key=lambda direction: (
                vote_weight[direction],
                direction.value,
            ),
        )
        loser = _opposite(winner)
        total_vote = vote_weight[winner] + vote_weight[loser]
        if total_vote <= 0:
            rejected.append({
                "market": market.value,
                "instrument": instrument,
                "horizon_seconds": horizon,
                "reason": "ZERO_CONFIDENCE_GROUP",
            })
            continue
        consensus = vote_weight[winner] / total_vote
        if consensus < consensus_floor:
            rejected.append({
                "market": market.value,
                "instrument": instrument,
                "horizon_seconds": horizon,
                "reason": "INSUFFICIENT_DIRECTIONAL_CONSENSUS",
                "consensus": str(consensus),
            })
            continue

        supporters = [
            member
            for member in by_model.values()
            if member.direction is winner and member.expected_net_return > 0
        ]
        independent = {member.source_model for member in supporters}
        if len(independent) < min_independent_models:
            rejected.append({
                "market": market.value,
                "instrument": instrument,
                "horizon_seconds": horizon,
                "reason": "INSUFFICIENT_INDEPENDENT_POSITIVE_MODELS",
                "supporters": len(independent),
            })
            continue

        weight_sum = sum(
            (member.confidence for member in supporters),
            Decimal("0"),
        )
        if weight_sum <= 0:
            rejected.append({
                "market": market.value,
                "instrument": instrument,
                "horizon_seconds": horizon,
                "reason": "ZERO_SUPPORT_WEIGHT",
            })
            continue

        gross = sum(
            (
                member.expected_gross_return * member.confidence
                for member in supporters
            ),
            Decimal("0"),
        ) / weight_sum
        costs = sum(
            (
                member.estimated_round_trip_cost_return * member.confidence
                for member in supporters
            ),
            Decimal("0"),
        ) / weight_sum
        expected_net = gross - costs
        if expected_net < edge_floor:
            rejected.append({
                "market": market.value,
                "instrument": instrument,
                "horizon_seconds": horizon,
                "reason": "INSUFFICIENT_ENSEMBLE_AFTER_COST_EDGE",
                "expected_net_return": str(expected_net),
            })
            continue

        mean_confidence = weight_sum / Decimal(len(supporters))
        ensemble_confidence = mean_confidence * consensus
        models = tuple(sorted(independent))
        evidence = tuple(sorted(member.evidence_id for member in supporters))
        families = tuple(sorted({member.strategy_family for member in supporters}))
        evidence_digest = hashlib.sha256(
            "|".join(evidence).encode("utf-8")
        ).hexdigest()
        candidate_digest = hashlib.sha256(
            (
                f"{market.value}|{instrument}|{winner.value}|{horizon}|"
                f"{','.join(models)}|{evidence_digest}"
            ).encode("utf-8")
        ).hexdigest()[:24]

        groups = {member.correlation_group for member in supporters}
        correlation_group = (
            next(iter(groups))
            if len(groups) == 1
            else f"{market.value}:{instrument}"
        )

        opportunities.append(
            Opportunity(
                market=market,
                instrument=instrument,
                candidate_id=f"ensemble:{candidate_digest}",
                strategy_family="ensemble[" + ",".join(families) + "]",
                direction=winner,
                generated_utc=max(
                    _utc(member.generated_utc, name="generated_utc")
                    for member in supporters
                ),
                valid_until_utc=min(
                    _utc(member.valid_until_utc, name="valid_until_utc")
                    for member in supporters
                ),
                horizon_seconds=horizon,
                expected_gross_return=gross,
                estimated_round_trip_cost_return=costs,
                confidence=ensemble_confidence,
                max_loss_return=min(member.max_loss_return for member in supporters),
                evidence_id=f"ensemble-sha256:{evidence_digest}",
                correlation_group=correlation_group,
                paper_executable=all(
                    member.paper_executable for member in supporters
                ),
                component_models=models,
                component_evidence_ids=evidence,
                ensemble_consensus=consensus,
            )
        )

    opportunities.sort(
        key=lambda item: (
            item.risk_adjusted_score,
            item.expected_net_return,
            item.confidence,
            item.market.value,
            item.instrument,
        ),
        reverse=True,
    )
    return EnsembleBuildResult(
        opportunities=tuple(opportunities),
        rejected_groups=tuple(rejected),
        active_signal_count=len(active),
        expired_signal_count=expired,
    )

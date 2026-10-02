"""Venue-neutral opportunity ranking and shared PAPER research allocator.

Phase 162 separates *signal intelligence* from deterministic portfolio authority.
Crypto, US-equity and event-market adapters may all emit the same Opportunity
contract. Models/strategies estimate an opportunity; this module decides only
whether it clears comparable after-cost/risk constraints and fits the shared
logical portfolio.

No broker imports, credentials, network calls, order submission or live mode
exist here. The allocator cannot increase its own risk limits.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Mapping, Sequence


class Market(str, Enum):
    CRYPTO = "crypto"
    US_EQUITY = "us_equity"
    EVENT_CONTRACT = "event_contract"


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"
    YES = "yes"
    NO = "no"


def _decimal(value: object, *, name: str) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal")
    return value


def _utc(value: datetime, *, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class Opportunity:
    """One independently evidenced directional opportunity.

    expected_gross_return is the expected return *for the chosen direction*.
    For example, a SHORT candidate predicting a 2% price fall may express a
    positive 0.02 gross directional return. estimated_round_trip_cost_return is
    then subtracted to make all markets comparable after modeled friction.
    """

    market: Market
    instrument: str
    candidate_id: str
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
        if not isinstance(self.market, Market) or not isinstance(self.direction, Direction):
            raise ValueError("market/direction must use normalized enums")
        if not self.instrument.strip() or len(self.instrument) > 80:
            raise ValueError("invalid opportunity instrument")
        if not self.candidate_id.strip() or len(self.candidate_id) > 160:
            raise ValueError("invalid candidate id")
        if not self.strategy_family.strip() or len(self.strategy_family) > 120:
            raise ValueError("invalid strategy family")
        generated = _utc(self.generated_utc, name="generated_utc")
        valid_until = _utc(self.valid_until_utc, name="valid_until_utc")
        if valid_until <= generated:
            raise ValueError("opportunity validity must extend beyond generation")
        if type(self.horizon_seconds) is not int or self.horizon_seconds <= 0:
            raise ValueError("positive integer horizon required")
        gross = _decimal(self.expected_gross_return, name="expected_gross_return")
        costs = _decimal(
            self.estimated_round_trip_cost_return,
            name="estimated_round_trip_cost_return",
        )
        confidence = _decimal(self.confidence, name="confidence")
        max_loss = _decimal(self.max_loss_return, name="max_loss_return")
        if gross < Decimal("-1") or gross > Decimal("10"):
            raise ValueError("expected directional return outside research bounds")
        if costs < 0 or costs > Decimal("1"):
            raise ValueError("invalid modeled round-trip cost")
        if not Decimal("0") <= confidence <= Decimal("1"):
            raise ValueError("confidence must be within [0,1]")
        if not Decimal("0") < max_loss <= Decimal("1"):
            raise ValueError("max_loss_return must be within (0,1]")
        if not self.evidence_id.strip() or len(self.evidence_id) > 256:
            raise ValueError("immutable evidence id required")
        if not self.correlation_group.strip() or len(self.correlation_group) > 80:
            raise ValueError("correlation group required")
        if type(self.paper_executable) is not bool:
            raise ValueError("paper_executable must be boolean")

    @property
    def expected_net_return(self) -> Decimal:
        return self.expected_gross_return - self.estimated_round_trip_cost_return

    @property
    def risk_adjusted_score(self) -> Decimal:
        """Deterministic comparison score; not a forecast or order permission."""
        return (
            self.expected_net_return
            * self.confidence
            / self.max_loss_return
        )


@dataclass(frozen=True)
class AllocatorLimits:
    logical_capital_usd: Decimal = Decimal("100")
    max_total_exposure_usd: Decimal = Decimal("60")
    position_notional_usd: Decimal = Decimal("15")
    max_positions: int = 4
    min_expected_net_return: Decimal = Decimal("0.005")
    min_confidence: Decimal = Decimal("0.55")
    max_positions_per_correlation_group: int = 2
    max_market_exposure_usd: tuple[tuple[Market, Decimal], ...] = (
        (Market.CRYPTO, Decimal("45")),
        (Market.US_EQUITY, Decimal("45")),
        (Market.EVENT_CONTRACT, Decimal("30")),
    )

    def __post_init__(self) -> None:
        capital = _decimal(self.logical_capital_usd, name="logical_capital_usd")
        exposure = _decimal(
            self.max_total_exposure_usd,
            name="max_total_exposure_usd",
        )
        position = _decimal(self.position_notional_usd, name="position_notional_usd")
        min_edge = _decimal(
            self.min_expected_net_return,
            name="min_expected_net_return",
        )
        min_conf = _decimal(self.min_confidence, name="min_confidence")
        if not Decimal("0") < position <= exposure <= capital:
            raise ValueError("position/exposure/capital limits are inconsistent")
        if type(self.max_positions) is not int or self.max_positions < 1:
            raise ValueError("max_positions must be a positive integer")
        if (
            type(self.max_positions_per_correlation_group) is not int
            or self.max_positions_per_correlation_group < 1
        ):
            raise ValueError("invalid correlation-group position cap")
        if min_edge < 0 or min_edge > Decimal("1"):
            raise ValueError("invalid minimum expected net return")
        if not Decimal("0") <= min_conf <= Decimal("1"):
            raise ValueError("invalid minimum confidence")
        seen: set[Market] = set()
        for market, cap in self.max_market_exposure_usd:
            if not isinstance(market, Market) or market in seen:
                raise ValueError("market exposure caps must be unique normalized markets")
            seen.add(market)
            cap = _decimal(cap, name="market exposure cap")
            if cap < position or cap > capital:
                raise ValueError("market exposure cap outside portfolio bounds")
        if seen != set(Market):
            raise ValueError("every market requires an explicit exposure cap")

    def market_caps(self) -> dict[Market, Decimal]:
        return dict(self.max_market_exposure_usd)


@dataclass(frozen=True)
class SelectedOpportunity:
    opportunity: Opportunity
    allocated_notional_usd: Decimal
    score: Decimal


@dataclass(frozen=True)
class RejectedOpportunity:
    opportunity: Opportunity
    reason: str


@dataclass(frozen=True)
class AllocationDecision:
    as_of_utc: datetime
    mode: str
    selected: tuple[SelectedOpportunity, ...]
    rejected: tuple[RejectedOpportunity, ...]
    total_exposure_usd: Decimal
    market_exposure_usd: Mapping[Market, Decimal]
    broker_order_submission: str = "DISABLED"
    live_trading: str = "UNAVAILABLE"


def allocate_opportunities(
    opportunities: Sequence[Opportunity],
    *,
    as_of: datetime,
    limits: AllocatorLimits = AllocatorLimits(),
    mode: str = "research",
) -> AllocationDecision:
    """Rank multiple markets together and allocate a shared logical bankroll.

    mode='paper' requires each selected opportunity to have an independently
    verified PAPER execution adapter. Research mode may rank non-executable
    candidates but still cannot submit anything.
    """
    now = _utc(as_of, name="as_of")
    if mode not in ("research", "paper"):
        raise ValueError("allocator mode must be research or paper")
    items = tuple(opportunities)
    if len(items) != len({item.candidate_id for item in items}):
        raise ValueError("candidate ids must be unique within one allocation cycle")

    rejected: list[RejectedOpportunity] = []
    eligible: list[Opportunity] = []
    for item in items:
        if not isinstance(item, Opportunity):
            raise ValueError("allocator accepts only normalized Opportunity records")
        if _utc(item.generated_utc, name="generated_utc") > now:
            rejected.append(RejectedOpportunity(item, "FUTURE_EVIDENCE_TIMESTAMP"))
        elif _utc(item.valid_until_utc, name="valid_until_utc") <= now:
            rejected.append(RejectedOpportunity(item, "STALE_OPPORTUNITY"))
        elif item.expected_net_return < limits.min_expected_net_return:
            rejected.append(RejectedOpportunity(item, "INSUFFICIENT_AFTER_COST_EDGE"))
        elif item.confidence < limits.min_confidence:
            rejected.append(RejectedOpportunity(item, "INSUFFICIENT_CONFIDENCE"))
        elif mode == "paper" and not item.paper_executable:
            rejected.append(RejectedOpportunity(item, "PAPER_ADAPTER_NOT_VERIFIED"))
        else:
            eligible.append(item)

    eligible.sort(
        key=lambda item: (
            item.risk_adjusted_score,
            item.expected_net_return,
            item.confidence,
            item.candidate_id,
        ),
        reverse=True,
    )

    market_caps = limits.market_caps()
    market_exposure = {market: Decimal("0") for market in Market}
    group_counts: dict[str, int] = {}
    selected: list[SelectedOpportunity] = []
    total = Decimal("0")

    for item in eligible:
        position = limits.position_notional_usd
        if len(selected) >= limits.max_positions:
            rejected.append(RejectedOpportunity(item, "MAX_POSITION_COUNT"))
            continue
        if total + position > limits.max_total_exposure_usd:
            rejected.append(RejectedOpportunity(item, "TOTAL_EXPOSURE_CAP"))
            continue
        if market_exposure[item.market] + position > market_caps[item.market]:
            rejected.append(RejectedOpportunity(item, "MARKET_EXPOSURE_CAP"))
            continue
        count = group_counts.get(item.correlation_group, 0)
        if count >= limits.max_positions_per_correlation_group:
            rejected.append(RejectedOpportunity(item, "CORRELATION_GROUP_CAP"))
            continue

        selected.append(
            SelectedOpportunity(
                opportunity=item,
                allocated_notional_usd=position,
                score=item.risk_adjusted_score,
            )
        )
        total += position
        market_exposure[item.market] += position
        group_counts[item.correlation_group] = count + 1

    return AllocationDecision(
        as_of_utc=now,
        mode=mode,
        selected=tuple(selected),
        rejected=tuple(rejected),
        total_exposure_usd=total,
        market_exposure_usd=market_exposure,
    )

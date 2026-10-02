"""Venue-neutral opportunity ranking and shared PAPER research allocator.

Phase 162 separates signal intelligence from deterministic portfolio authority.
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

from .cross_market_risk import (
    CrossMarketRiskLimits,
    assess_new_risk,
)


class Market(str, Enum):
    CRYPTO = "crypto"
    US_EQUITY = "us_equity"
    EVENT_CONTRACT = "event_contract"


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"
    YES = "yes"
    NO = "no"


_MARKET_TO_RISK_LANE = {
    Market.CRYPTO: "crypto",
    Market.US_EQUITY: "us_equity",
    Market.EVENT_CONTRACT: "kalshi_event_contract",
}


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

    expected_gross_return is the expected return for the chosen direction.
    For example, a SHORT candidate predicting a 2% price fall may express a
    positive 0.02 gross directional return. estimated_round_trip_cost_return is
    then subtracted to make all markets comparable after modeled friction.

    paper_executable means a separately validated PAPER/DEMO adapter exists for
    this exact direction/instrument contract. It is not live authorization.
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
        if not isinstance(self.instrument, str) or not self.instrument.strip() or len(self.instrument) > 80:
            raise ValueError("invalid opportunity instrument")
        if not isinstance(self.candidate_id, str) or not self.candidate_id.strip() or len(self.candidate_id) > 160:
            raise ValueError("invalid candidate id")
        if not isinstance(self.strategy_family, str) or not self.strategy_family.strip() or len(self.strategy_family) > 120:
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
        if not isinstance(self.evidence_id, str) or not self.evidence_id.strip() or len(self.evidence_id) > 256:
            raise ValueError("immutable evidence id required")
        if not isinstance(self.correlation_group, str) or not self.correlation_group.strip() or len(self.correlation_group) > 80:
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
    shared_risk_limits: CrossMarketRiskLimits = CrossMarketRiskLimits()

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
        if not isinstance(self.shared_risk_limits, CrossMarketRiskLimits):
            raise ValueError("explicit shared cross-market risk limits required")
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
class AllocationPortfolioState:
    """Current shared portfolio state before this allocation cycle.

    notional_exposure_usd controls capital concentration. risk_exposure_usd is
    the maximum-loss budget already reserved for the existing positions and is
    checked by the existing cross_market_risk governor.
    """

    notional_exposure_usd: Mapping[Market, Decimal]
    risk_exposure_usd: Mapping[Market, Decimal]
    open_positions: int
    open_instruments: frozenset[tuple[Market, str]]
    marked_equity_usd: Decimal
    daily_anchor_equity_usd: Decimal
    peak_equity_usd: Decimal
    operator_halted: bool = False

    def __post_init__(self) -> None:
        if type(self.open_positions) is not int or self.open_positions < 0:
            raise ValueError("invalid open position count")
        if type(self.operator_halted) is not bool:
            raise ValueError("operator halt must be boolean")
        if not isinstance(self.open_instruments, frozenset):
            raise ValueError("open instruments must be a frozenset")
        for item in self.open_instruments:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], Market)
                or not isinstance(item[1], str)
                or not item[1]
            ):
                raise ValueError("invalid open instrument identity")
        for mapping, label in (
            (self.notional_exposure_usd, "notional exposure"),
            (self.risk_exposure_usd, "risk exposure"),
        ):
            if set(mapping) - set(Market):
                raise ValueError(f"unknown market in {label}")
            for market in Market:
                value = mapping.get(market, Decimal("0"))
                if _decimal(value, name=label) < 0:
                    raise ValueError(f"negative {label}")
        marked = _decimal(self.marked_equity_usd, name="marked equity")
        daily = _decimal(self.daily_anchor_equity_usd, name="daily anchor")
        peak = _decimal(self.peak_equity_usd, name="peak equity")
        if min(marked, daily, peak) < 0:
            raise ValueError("portfolio equity values cannot be negative")
        if peak < marked:
            raise ValueError("peak equity cannot be below current marked equity")

    @classmethod
    def fresh(cls, capital_usd: Decimal) -> "AllocationPortfolioState":
        capital = _decimal(capital_usd, name="fresh capital")
        if capital <= 0:
            raise ValueError("fresh portfolio capital must be positive")
        return cls(
            notional_exposure_usd={},
            risk_exposure_usd={},
            open_positions=0,
            open_instruments=frozenset(),
            marked_equity_usd=capital,
            daily_anchor_equity_usd=capital,
            peak_equity_usd=capital,
            operator_halted=False,
        )


@dataclass(frozen=True)
class SelectedOpportunity:
    opportunity: Opportunity
    allocated_notional_usd: Decimal
    reserved_max_loss_usd: Decimal
    score: Decimal
    shared_risk_receipt: Mapping[str, object]


@dataclass(frozen=True)
class RejectedOpportunity:
    opportunity: Opportunity
    reason: str
    details: tuple[str, ...] = ()


@dataclass(frozen=True)
class AllocationDecision:
    as_of_utc: datetime
    mode: str
    selected: tuple[SelectedOpportunity, ...]
    rejected: tuple[RejectedOpportunity, ...]
    total_exposure_usd: Decimal
    market_exposure_usd: Mapping[Market, Decimal]
    total_reserved_risk_usd: Decimal
    market_reserved_risk_usd: Mapping[Market, Decimal]
    projected_open_positions: int
    broker_order_submission: str = "DISABLED"
    live_trading: str = "UNAVAILABLE"


def allocate_opportunities(
    opportunities: Sequence[Opportunity],
    *,
    as_of: datetime,
    limits: AllocatorLimits = AllocatorLimits(),
    mode: str = "research",
    portfolio: AllocationPortfolioState | None = None,
) -> AllocationDecision:
    """Rank multiple markets together and allocate one shared logical bankroll.

    mode='paper' requires each selected opportunity to have an independently
    verified PAPER/DEMO execution adapter. Research mode may rank non-executable
    candidates but still cannot submit anything.

    Every selected candidate is also passed through the existing deterministic
    cross-market risk governor using its requested maximum-loss budget.
    """
    now = _utc(as_of, name="as_of")
    if mode not in ("research", "paper"):
        raise ValueError("allocator mode must be research or paper")
    items = tuple(opportunities)
    if len(items) != len({item.candidate_id for item in items}):
        raise ValueError("candidate ids must be unique within one allocation cycle")
    state = portfolio or AllocationPortfolioState.fresh(limits.logical_capital_usd)

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
    market_exposure = {
        market: state.notional_exposure_usd.get(market, Decimal("0"))
        for market in Market
    }
    risk_exposure = {
        market: state.risk_exposure_usd.get(market, Decimal("0"))
        for market in Market
    }
    group_counts: dict[str, int] = {}
    selected: list[SelectedOpportunity] = []
    total = sum(market_exposure.values(), Decimal("0"))
    projected_open_positions = state.open_positions
    occupied = set(state.open_instruments)

    if total > limits.max_total_exposure_usd:
        raise ValueError("current notional exposure already exceeds allocator cap")

    for item in eligible:
        position = limits.position_notional_usd
        identity = (item.market, item.instrument)

        if identity in occupied:
            rejected.append(RejectedOpportunity(item, "DUPLICATE_INSTRUMENT_EXPOSURE"))
            continue
        if projected_open_positions >= limits.max_positions:
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

        # The common risk kernel works in maximum-loss dollars, while allocator
        # concentration limits above work in gross notional dollars.
        reserved_max_loss = position * item.max_loss_return
        lane = _MARKET_TO_RISK_LANE[item.market]
        risk_by_lane = {
            _MARKET_TO_RISK_LANE[market]: value
            for market, value in risk_exposure.items()
        }
        risk_receipt = assess_new_risk(
            lane=lane,
            proposed_max_loss_usd=reserved_max_loss,
            exposure_by_lane=risk_by_lane,
            open_positions=projected_open_positions,
            marked_equity_usd=state.marked_equity_usd,
            daily_anchor_equity_usd=state.daily_anchor_equity_usd,
            peak_equity_usd=state.peak_equity_usd,
            operator_halted=state.operator_halted,
            limits=limits.shared_risk_limits,
        )
        if risk_receipt["risk_admissible"] is not True:
            rejected.append(
                RejectedOpportunity(
                    item,
                    "SHARED_RISK_GOVERNOR_REJECTED",
                    tuple(risk_receipt["rejection_reasons"]),
                )
            )
            continue

        selected.append(
            SelectedOpportunity(
                opportunity=item,
                allocated_notional_usd=position,
                reserved_max_loss_usd=reserved_max_loss,
                score=item.risk_adjusted_score,
                shared_risk_receipt=risk_receipt,
            )
        )
        occupied.add(identity)
        total += position
        market_exposure[item.market] += position
        risk_exposure[item.market] += reserved_max_loss
        projected_open_positions += 1
        group_counts[item.correlation_group] = count + 1

    return AllocationDecision(
        as_of_utc=now,
        mode=mode,
        selected=tuple(selected),
        rejected=tuple(rejected),
        total_exposure_usd=total,
        market_exposure_usd=market_exposure,
        total_reserved_risk_usd=sum(risk_exposure.values(), Decimal("0")),
        market_reserved_risk_usd=risk_exposure,
        projected_open_positions=projected_open_positions,
    )

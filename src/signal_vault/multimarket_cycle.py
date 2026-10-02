"""Phase 162 multi-market cycle planner.

The planner is the common bridge between independent market intelligence and
venue-specific PAPER adapters. It consumes normalized Opportunities, runs the
shared allocator, then emits deterministic idempotent execution intents.

It deliberately does NOT call brokers. Execution adapters must independently
re-validate venue rules, account state, prices, and idempotency before any PAPER
POST. Live mode is not implemented.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Mapping, Sequence

from .opportunity_engine import (
    AllocationDecision,
    AllocationPortfolioState,
    AllocatorLimits,
    Direction,
    Market,
    Opportunity,
    allocate_opportunities,
)


@dataclass(frozen=True)
class PaperRoute:
    market: Market
    route_id: str
    verified_for_paper: bool
    supported_directions: tuple[Direction, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.market, Market):
            raise ValueError("route market must be normalized")
        if not self.route_id.strip() or len(self.route_id) > 120:
            raise ValueError("invalid route id")
        if type(self.verified_for_paper) is not bool:
            raise ValueError("verified_for_paper must be boolean")
        if any(not isinstance(direction, Direction) for direction in self.supported_directions):
            raise ValueError("route directions must use normalized Direction values")
        if len(self.supported_directions) != len(set(self.supported_directions)):
            raise ValueError("route directions must be unique")

    def allows_direction(self, direction: Direction) -> bool:
        if not isinstance(direction, Direction):
            return False
        if self.supported_directions:
            return direction in self.supported_directions
        # Conservative defaults: current crypto/stock PAPER lanes are long-entry
        # lanes unless an instrument-specific shortability preflight explicitly
        # supplies SHORT. Kalshi DEMO supports YES and NO contracts.
        if self.market is Market.EVENT_CONTRACT:
            return direction in (Direction.YES, Direction.NO)
        return direction is Direction.LONG


@dataclass(frozen=True)
class PlannedExecutionIntent:
    client_intent_id: str
    market: Market
    instrument: str
    direction: Direction
    route_id: str
    notional_usd: Decimal
    reserved_max_loss_usd: Decimal
    candidate_id: str
    evidence_id: str
    generated_utc: datetime
    expected_net_return: Decimal
    paper_only: bool = True


@dataclass(frozen=True)
class MultiMarketPlan:
    allocation: AllocationDecision
    execution_intents: tuple[PlannedExecutionIntent, ...]
    unrouteable_selected_candidate_ids: tuple[str, ...]
    order_submission: str = "DISABLED"
    live_trading: str = "UNAVAILABLE"


def _intent_id(
    *,
    selected,
    route: PaperRoute,
    as_of: datetime,
) -> str:
    item = selected.opportunity
    payload = {
        "version": "phase162-multimarket-intent-v1",
        "as_of_utc": as_of.isoformat(),
        "market": item.market.value,
        "instrument": item.instrument,
        "direction": item.direction.value,
        "candidate_id": item.candidate_id,
        "evidence_id": item.evidence_id,
        "route_id": route.route_id,
        "notional_usd": str(selected.allocated_notional_usd),
        "reserved_max_loss_usd": str(selected.reserved_max_loss_usd),
        "expected_net_return": str(item.expected_net_return),
    }
    digest = hashlib.sha256(
        (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
        .encode("utf-8")
    ).hexdigest()
    return "sv162-" + digest[:40]


def build_multimarket_plan(
    opportunities: Sequence[Opportunity],
    *,
    as_of: datetime,
    limits: AllocatorLimits = AllocatorLimits(),
    routes: Sequence[PaperRoute] = (),
    mode: str = "research",
    portfolio: AllocationPortfolioState | None = None,
) -> MultiMarketPlan:
    """Build one shared research/PAPER plan across every enabled market lane."""
    if mode not in ("research", "paper"):
        raise ValueError("only research or paper planning exists")
    route_items = tuple(routes)
    if len(route_items) != len({route.market for route in route_items}):
        raise ValueError("at most one explicit route per market")
    route_map: Mapping[Market, PaperRoute] = {
        route.market: route for route in route_items
    }

    allocation = allocate_opportunities(
        opportunities,
        as_of=as_of,
        limits=limits,
        mode=mode,
        portfolio=portfolio,
    )
    intents: list[PlannedExecutionIntent] = []
    unrouteable: list[str] = []

    for selected in allocation.selected:
        item = selected.opportunity
        route = route_map.get(item.market)
        if route is None:
            unrouteable.append(item.candidate_id)
            continue
        if mode == "paper" and not route.verified_for_paper:
            unrouteable.append(item.candidate_id)
            continue
        if not route.allows_direction(item.direction):
            unrouteable.append(item.candidate_id)
            continue

        intents.append(
            PlannedExecutionIntent(
                client_intent_id=_intent_id(
                    selected=selected,
                    route=route,
                    as_of=allocation.as_of_utc,
                ),
                market=item.market,
                instrument=item.instrument,
                direction=item.direction,
                route_id=route.route_id,
                notional_usd=selected.allocated_notional_usd,
                reserved_max_loss_usd=selected.reserved_max_loss_usd,
                candidate_id=item.candidate_id,
                evidence_id=item.evidence_id,
                generated_utc=allocation.as_of_utc,
                expected_net_return=item.expected_net_return,
            )
        )

    if len({intent.client_intent_id for intent in intents}) != len(intents):
        raise AssertionError("deterministic multi-market intent ids collided")

    return MultiMarketPlan(
        allocation=allocation,
        execution_intents=tuple(intents),
        unrouteable_selected_candidate_ids=tuple(sorted(unrouteable)),
    )

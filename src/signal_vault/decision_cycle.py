"""One Signal Vault decision cycle across crypto, US equities, and events.

This is the portfolio brain boundary:
  many market-specific model/rule signals
      -> independent-model consensus
      -> comparable after-cost opportunities
      -> one shared allocator/risk governor
      -> deterministic PAPER execution intents

The cycle never calls a broker. PAPER adapters consume the resulting intents in
a separate execution step with their own provider preflight/idempotency rules.
Live mode does not exist here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Sequence

from .ensemble_signals import (
    EnsembleBuildResult,
    ModelSignal,
    build_ensemble_opportunities,
)
from .multimarket_cycle import (
    MultiMarketPlan,
    PaperRoute,
    build_multimarket_plan,
)
from .opportunity_engine import (
    AllocationPortfolioState,
    AllocatorLimits,
)


@dataclass(frozen=True)
class DecisionCycleResult:
    ensemble: EnsembleBuildResult
    plan: MultiMarketPlan
    input_signal_count: int
    mode: str
    order_submission: str = "DISABLED"
    live_trading: str = "UNAVAILABLE"

    def summary(self) -> dict[str, object]:
        return {
            "kind": "PHASE162_SIMULTANEOUS_MULTIMARKET_DECISION_CYCLE_NO_ORDER",
            "mode": self.mode,
            "input_signal_count": self.input_signal_count,
            "active_signal_count": self.ensemble.active_signal_count,
            "expired_signal_count": self.ensemble.expired_signal_count,
            "ensemble_opportunity_count": len(self.ensemble.opportunities),
            "ensemble_rejected_group_count": len(
                self.ensemble.rejected_groups
            ),
            "selected_opportunity_count": len(
                self.plan.allocation.selected
            ),
            "planned_execution_intent_count": len(
                self.plan.execution_intents
            ),
            "unrouteable_selected_candidate_ids": list(
                self.plan.unrouteable_selected_candidate_ids
            ),
            "selected": [
                {
                    "candidate_id": item.opportunity.candidate_id,
                    "market": item.opportunity.market.value,
                    "instrument": item.opportunity.instrument,
                    "direction": item.opportunity.direction.value,
                    "strategy_family": item.opportunity.strategy_family,
                    "component_models": list(
                        item.opportunity.component_models
                    ),
                    "ensemble_consensus": str(
                        item.opportunity.ensemble_consensus
                    ),
                    "expected_net_return": str(
                        item.opportunity.expected_net_return
                    ),
                    "confidence": str(item.opportunity.confidence),
                    "allocated_notional_usd": str(
                        item.allocated_notional_usd
                    ),
                    "reserved_max_loss_usd": str(
                        item.reserved_max_loss_usd
                    ),
                    "shared_risk_admissible":
                        item.shared_risk_receipt["risk_admissible"],
                }
                for item in self.plan.allocation.selected
            ],
            "order_submission": "DISABLED",
            "live_trading": "UNAVAILABLE",
            "decision_cycle_is_not_order_authorization": True,
        }


def run_decision_cycle(
    signals: Sequence[ModelSignal],
    *,
    as_of: datetime,
    routes: Sequence[PaperRoute] = (),
    portfolio: AllocationPortfolioState | None = None,
    allocator_limits: AllocatorLimits = AllocatorLimits(),
    mode: str = "research",
    min_independent_models: int = 2,
    min_consensus: Decimal = Decimal("0.60"),
    min_model_ensemble_net_return: Decimal = Decimal("0.001"),
) -> DecisionCycleResult:
    """Evaluate all enabled markets in one deterministic decision cycle."""
    if mode not in ("research", "paper"):
        raise ValueError("decision cycle supports research or paper only")
    items = tuple(signals)
    ensemble = build_ensemble_opportunities(
        items,
        as_of=as_of,
        min_independent_models=min_independent_models,
        min_consensus=min_consensus,
        min_expected_net_return=min_model_ensemble_net_return,
    )
    plan = build_multimarket_plan(
        ensemble.opportunities,
        as_of=as_of,
        limits=allocator_limits,
        routes=routes,
        mode=mode,
        portfolio=portfolio,
    )
    return DecisionCycleResult(
        ensemble=ensemble,
        plan=plan,
        input_signal_count=len(items),
        mode=mode,
    )

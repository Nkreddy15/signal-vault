"""Pure multi-market readiness reporting.

This module converts evidence flags into an operator-facing checklist for
crypto, US equities, and Kalshi. It never places orders and it does not decide
whether the owner should trade. A lane can only be reported as technically
eligible for a later live-activation review when every predeclared prerequisite
is evidenced.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

LANES=("crypto","us_equity","kalshi_event_contract")


@dataclass(frozen=True)
class LaneEvidence:
    historical_dataset_verified: bool
    historical_walk_forward_complete: bool
    frozen_model_or_ruleset: bool
    prospective_or_shadow_complete: bool
    paper_or_demo_execution_validated: bool
    restart_and_unknown_result_recovery_validated: bool
    provider_reconciliation_validated: bool
    shared_risk_governor_validated: bool
    live_credentials_configured: bool = False
    owner_live_authorization_recorded: bool = False

    def __post_init__(self) -> None:
        for value in asdict(self).values():
            if type(value) is not bool:
                raise ValueError("readiness evidence must be explicit booleans")


_REQUIRED_BEFORE_LIVE_REVIEW=(
    "historical_dataset_verified",
    "historical_walk_forward_complete",
    "frozen_model_or_ruleset",
    "prospective_or_shadow_complete",
    "paper_or_demo_execution_validated",
    "restart_and_unknown_result_recovery_validated",
    "provider_reconciliation_validated",
    "shared_risk_governor_validated",
)


def assess_lane_readiness(lane:str,evidence:LaneEvidence) -> dict[str,object]:
    if lane not in LANES:
        raise ValueError("unsupported market lane")
    values=asdict(evidence)
    blockers=[name for name in _REQUIRED_BEFORE_LIVE_REVIEW if not values[name]]
    technically_ready_for_live_activation_review=not blockers
    live_activation_permitted=(
        technically_ready_for_live_activation_review
        and evidence.live_credentials_configured
        and evidence.owner_live_authorization_recorded
    )
    return {
        "kind":"MARKET_LANE_READINESS_NOT_TRADING_RECOMMENDATION",
        "lane":lane,
        "evidence":values,
        "technical_blockers_before_live_activation_review":blockers,
        "technically_ready_for_live_activation_review":
            technically_ready_for_live_activation_review,
        "live_credentials_configured":evidence.live_credentials_configured,
        "owner_live_authorization_recorded":evidence.owner_live_authorization_recorded,
        "live_activation_permitted":live_activation_permitted,
        "automatic_live_activation":"DISABLED",
        "readiness_is_not_expected_profit_or_trading_advice":True,
    }


def multimarket_readiness(
    evidence_by_lane:dict[str,LaneEvidence],
) -> dict[str,object]:
    if set(evidence_by_lane)!=set(LANES):
        raise ValueError("readiness report requires all three market lanes")
    lanes={
        lane:assess_lane_readiness(lane,evidence_by_lane[lane])
        for lane in LANES
    }
    return {
        "kind":"SIGNAL_VAULT_MULTIMARKET_READINESS_NOT_ORDER_AUTHORIZATION",
        "lanes":lanes,
        "all_lanes_technically_ready_for_live_activation_review":all(
            item["technically_ready_for_live_activation_review"]
            for item in lanes.values()
        ),
        "any_live_activation_permitted":any(
            item["live_activation_permitted"] for item in lanes.values()
        ),
        "automatic_live_activation":"DISABLED",
    }

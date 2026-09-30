"""Final conservative Kalshi technical-readiness composition.

Combines three independently produced receipts:
- historical research readiness (Phase 63),
- prospective shadow evidence (Phase 65),
- DEMO execution mechanics (Phase 64).

Only a candidate that is both historically confirmed and prospectively passing
can satisfy the frozen-model/ruleset evidence. DEMO mechanics are separate from
strategy evidence. Even when every technical prerequisite is complete, LIVE
activation remains impossible here because live credentials and owner live
authorization are hardcoded false.
"""
from __future__ import annotations

from typing import Mapping

from .multimarket_readiness import LaneEvidence, assess_lane_readiness


def compose_kalshi_final_technical_readiness(
    historical:Mapping[str,object],
    prospective:Mapping[str,object],
    demo_execution:Mapping[str,object],
)->dict[str,object]:
    if (
        historical.get("kind")
        !="KALSHI_RESEARCH_READINESS_RECEIPT_NOT_ORDER_AUTHORIZATION"
        or historical.get("demo_order_submission")!="DISABLED"
        or historical.get("live_order_submission")!="DISABLED"
        or historical.get("automatic_live_activation")!="DISABLED"
    ):
        raise ValueError("invalid Kalshi historical readiness receipt")
    if (
        prospective.get("kind")!="KALSHI_PROSPECTIVE_SHADOW_GATE_NO_ORDER"
        or prospective.get("candidate_added_by_prospective_results") is not False
        or prospective.get("candidate_ranking_performed") is not False
        or prospective.get("automatic_candidate_selection")!="DISABLED"
        or prospective.get("demo_order_submission")!="DISABLED"
        or prospective.get("live_order_submission")!="DISABLED"
    ):
        raise ValueError("invalid Kalshi prospective-shadow receipt")
    if (
        demo_execution.get("kind")
        !="KALSHI_DEMO_EXECUTION_ACCEPTANCE_NO_LIVE_AUTHORITY"
        or demo_execution.get("automatic_live_activation")!="DISABLED"
        or demo_execution.get("live_order_submission")!="DISABLED"
        or demo_execution.get("live_credentials_configured") is not False
        or demo_execution.get("owner_live_authorization_recorded") is not False
    ):
        raise ValueError("invalid Kalshi DEMO execution acceptance receipt")

    historical_candidates=historical.get(
        "historically_confirmed_fixed_candidates"
    )
    prospective_candidates=prospective.get(
        "candidates_passing_prospective_shadow"
    )
    if (
        not isinstance(historical_candidates,list)
        or not isinstance(prospective_candidates,list)
        or any(not isinstance(x,str) or not x for x in historical_candidates)
        or any(not isinstance(x,str) or not x for x in prospective_candidates)
    ):
        raise ValueError("invalid Kalshi fixed candidate lists")
    if (
        len(set(historical_candidates))!=len(historical_candidates)
        or len(set(prospective_candidates))!=len(prospective_candidates)
        or any(x not in historical_candidates for x in prospective_candidates)
    ):
        raise ValueError("prospective Kalshi candidates must be historical survivors")

    final_candidates=[
        x for x in historical_candidates if x in prospective_candidates
    ]

    historical_dataset=historical.get("historical_depth_ready") is True
    historical_walk=historical.get(
        "historical_walk_forward_complete"
    ) is True
    prospective_complete=(
        prospective.get("prospective_or_shadow_complete") is True
        and bool(final_candidates)
    )
    demo_validated=demo_execution.get("demo_execution_validated") is True
    restart_validated=demo_execution.get(
        "restart_and_unknown_result_recovery_validated"
    ) is True
    reconciliation_validated=demo_execution.get(
        "provider_reconciliation_validated"
    ) is True

    evidence=LaneEvidence(
        historical_dataset_verified=historical_dataset,
        historical_walk_forward_complete=historical_walk,
        frozen_model_or_ruleset=bool(final_candidates),
        prospective_or_shadow_complete=prospective_complete,
        paper_or_demo_execution_validated=demo_validated,
        restart_and_unknown_result_recovery_validated=restart_validated,
        provider_reconciliation_validated=reconciliation_validated,
        shared_risk_governor_validated=True,
        live_credentials_configured=False,
        owner_live_authorization_recorded=False,
    )
    lane=assess_lane_readiness("kalshi_event_contract",evidence)
    if lane["live_activation_permitted"]:
        raise AssertionError("Kalshi technical receipt must never activate live trading")

    technically_ready=lane["technically_ready_for_live_activation_review"]
    return {
        "kind":"KALSHI_FINAL_TECHNICAL_READINESS_NOT_LIVE_AUTHORIZATION",
        "fixed_candidates_surviving_historical_and_prospective_gates":
            final_candidates,
        "shared_lane_readiness":lane,
        "technically_ready_for_separate_live_activation_review":
            technically_ready,
        "live_credentials_configured":False,
        "owner_live_authorization_recorded":False,
        "live_activation_permitted":False,
        "automatic_live_activation":"DISABLED",
        "live_order_submission":"DISABLED",
        "next_action":(
            "SEPARATE_OWNER_LIVE_ACTIVATION_REVIEW_REQUIRED"
            if technically_ready else
            "TECHNICAL_EVIDENCE_INCOMPLETE"
        ),
        "readiness_is_not_expected_profit_or_trading_advice":True,
    }

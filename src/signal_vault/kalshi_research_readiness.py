"""Conservative Kalshi research-readiness receipt for the shared UI.

This adapter translates completed historical research artifacts into the same
LaneEvidence contract used by the multi-market readiness dashboard. It only
marks what the supplied evidence proves. In particular, historical success
never implies prospective/demo execution, restart recovery, provider
reconciliation, live credentials, or owner live authorization.
"""
from __future__ import annotations

from typing import Mapping

from .multimarket_readiness import LaneEvidence, assess_lane_readiness


def kalshi_research_readiness_receipt(
    depth_gate:Mapping[str,object],
    walk_forward:Mapping[str,object],
    untouched_confirmation:Mapping[str,object],
)->dict[str,object]:
    if (
        depth_gate.get("kind")
        !="KALSHI_HISTORICAL_DEPTH_GATE_PREDECLARED_NO_ORDER"
        or depth_gate.get("demo_execution_eligible") is not False
        or depth_gate.get("live_execution_eligible") is not False
        or depth_gate.get("order_submission")!="DISABLED"
    ):
        raise ValueError("invalid Kalshi historical depth-gate receipt")
    if (
        walk_forward.get("kind")
        !="OFFLINE_KALSHI_EXPANDING_WALK_FORWARD_RESEARCH"
        or walk_forward.get("resolved_market_count")!=50
        or walk_forward.get("historical_walk_forward_is_not_prospective_validation")
           is not True
        or walk_forward.get("strategy_selection_performed") is not False
        or walk_forward.get("demo_order_submission")!="DISABLED"
        or walk_forward.get("live_order_submission")!="DISABLED"
    ):
        raise ValueError("invalid Kalshi historical walk-forward receipt")
    if (
        untouched_confirmation.get("kind")
        !="KALSHI_UNTOUCHED_TEST_CONFIRMATION_NO_ORDER"
        or untouched_confirmation.get("candidate_added_by_untouched_test") is not False
        or untouched_confirmation.get("candidate_ranking_performed") is not False
        or untouched_confirmation.get("automatic_candidate_selection")!="DISABLED"
        or untouched_confirmation.get("demo_order_submission")!="DISABLED"
        or untouched_confirmation.get("live_order_submission")!="DISABLED"
    ):
        raise ValueError("invalid Kalshi untouched-confirmation receipt")

    depth_ready=(
        depth_gate.get("historical_depth_ready_for_fixed_strategy_research")
        is True
    )
    walk_ready=walk_forward.get("historical_walk_forward_complete") is True
    confirmed=untouched_confirmation.get(
        "candidates_confirmed_on_untouched_test"
    )
    if not isinstance(confirmed,list) or any(
        not isinstance(x,str) or not x for x in confirmed
    ):
        raise ValueError("invalid confirmed Kalshi candidate list")
    if len(set(confirmed))!=len(confirmed):
        raise ValueError("duplicate confirmed Kalshi candidate")

    historical_candidate_confirmed=bool(confirmed)
    ready_for_demo_design=(
        depth_ready and walk_ready and historical_candidate_confirmed
        and untouched_confirmation.get(
            "eligible_for_demo_execution_design_review"
        ) is True
    )

    evidence=LaneEvidence(
        historical_dataset_verified=depth_ready,
        historical_walk_forward_complete=walk_ready,
        frozen_model_or_ruleset=historical_candidate_confirmed,
        prospective_or_shadow_complete=False,
        paper_or_demo_execution_validated=False,
        restart_and_unknown_result_recovery_validated=False,
        provider_reconciliation_validated=False,
        shared_risk_governor_validated=True,
        live_credentials_configured=False,
        owner_live_authorization_recorded=False,
    )
    lane=assess_lane_readiness("kalshi_event_contract",evidence)
    if lane["live_activation_permitted"]:
        raise AssertionError("historical Kalshi research must never permit live activation")

    return {
        "kind":"KALSHI_RESEARCH_READINESS_RECEIPT_NOT_ORDER_AUTHORIZATION",
        "historical_depth_ready":depth_ready,
        "historical_walk_forward_complete":walk_ready,
        "historically_confirmed_fixed_candidates":list(confirmed),
        "historical_candidate_confirmed":historical_candidate_confirmed,
        "ready_for_separate_demo_execution_design_review":ready_for_demo_design,
        "shared_lane_readiness":lane,
        "prospective_or_shadow_complete":False,
        "demo_execution_validated":False,
        "restart_and_unknown_result_recovery_provider_validated":False,
        "provider_reconciliation_validated":False,
        "live_credentials_configured":False,
        "owner_live_authorization_recorded":False,
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "automatic_live_activation":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }

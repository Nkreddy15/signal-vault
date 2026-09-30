"""Conservative stock research-readiness receipt for the shared UI.

Historical source verification, expanding walk-forward, the frozen candidate
gate and untouched confirmation can establish historical research readiness.
They cannot establish prospective/shadow validation, PAPER execution quality,
provider reconciliation, live credentials, or owner live authorization.
"""
from __future__ import annotations

from typing import Mapping

from .multimarket_readiness import LaneEvidence, assess_lane_readiness


def equity_research_readiness_receipt(
    candidate_gate:Mapping[str,object],
    untouched_confirmation:Mapping[str,object],
    walk_forward:Mapping[str,object],
)->dict[str,object]:
    if (
        candidate_gate.get("kind")
        !="EQUITY_PREDECLARED_HISTORICAL_CANDIDATE_GATE_NO_ORDER"
        or candidate_gate.get("candidate_ranking_performed") is not False
        or candidate_gate.get("automatic_candidate_selection")!="DISABLED"
        or candidate_gate.get("untouched_test_accessed_for_candidate_selection") is not False
        or candidate_gate.get("broker_order_submission")!="DISABLED"
    ):
        raise ValueError("invalid stock historical candidate-gate receipt")
    if (
        untouched_confirmation.get("kind")
        !="EQUITY_UNTOUCHED_TEST_CONFIRMATION_NO_ORDER"
        or untouched_confirmation.get("candidate_added_by_untouched_test") is not False
        or untouched_confirmation.get("candidate_ranking_performed") is not False
        or untouched_confirmation.get("automatic_candidate_selection")!="DISABLED"
        or untouched_confirmation.get("paper_order_submission")!="DISABLED"
        or untouched_confirmation.get("live_order_submission")!="DISABLED"
    ):
        raise ValueError("invalid stock untouched-confirmation receipt")
    if (
        walk_forward.get("kind")
        !="OFFLINE_EXPANDING_WALK_FORWARD_SIX_STOCK_RESEARCH"
        or walk_forward.get("historical_walk_forward_complete") is not True
        or walk_forward.get("historical_walk_forward_is_not_prospective_validation")
           is not True
        or walk_forward.get("strategy_selection_performed") is not False
        or walk_forward.get("hyperparameter_optimization_performed") is not False
        or walk_forward.get("broker_order_submission")!="DISABLED"
        or walk_forward.get("live_trading")!="UNAVAILABLE"
    ):
        raise ValueError("invalid stock walk-forward receipt")

    eligible=candidate_gate.get("candidates_meeting_all_criteria")
    confirmed=untouched_confirmation.get(
        "candidates_confirmed_on_untouched_test"
    )
    if (
        not isinstance(eligible,list)
        or not isinstance(confirmed,list)
        or any(not isinstance(x,str) or not x for x in eligible)
        or any(not isinstance(x,str) or not x for x in confirmed)
        or len(set(eligible))!=len(eligible)
        or len(set(confirmed))!=len(confirmed)
        or any(x not in eligible for x in confirmed)
    ):
        raise ValueError("stock untouched candidates must be historical-gate survivors")

    historical_dataset_verified=True
    historical_walk_forward_complete=True
    frozen_model_or_ruleset=bool(confirmed)

    evidence=LaneEvidence(
        historical_dataset_verified=historical_dataset_verified,
        historical_walk_forward_complete=historical_walk_forward_complete,
        frozen_model_or_ruleset=frozen_model_or_ruleset,
        prospective_or_shadow_complete=False,
        paper_or_demo_execution_validated=False,
        restart_and_unknown_result_recovery_validated=False,
        provider_reconciliation_validated=False,
        shared_risk_governor_validated=True,
        live_credentials_configured=False,
        owner_live_authorization_recorded=False,
    )
    lane=assess_lane_readiness("us_equity",evidence)
    if lane["live_activation_permitted"]:
        raise AssertionError("historical stock research must never activate live trading")

    return {
        "kind":"EQUITY_RESEARCH_READINESS_RECEIPT_NOT_ORDER_AUTHORIZATION",
        "historical_dataset_verified":historical_dataset_verified,
        "historical_walk_forward_complete":historical_walk_forward_complete,
        "historically_confirmed_fixed_candidates":list(confirmed),
        "historical_candidate_confirmed":bool(confirmed),
        "ready_for_prospective_shadow_collection":bool(confirmed),
        "shared_lane_readiness":lane,
        "prospective_or_shadow_complete":False,
        "paper_execution_validated":False,
        "restart_and_unknown_result_recovery_provider_validated":False,
        "provider_reconciliation_validated":False,
        "live_credentials_configured":False,
        "owner_live_authorization_recorded":False,
        "paper_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "automatic_live_activation":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }

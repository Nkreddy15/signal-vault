"""Untouched-test confirmation for already-eligible Kalshi candidates.

This stage is intentionally downstream of the frozen Phase 61
development/validation candidate gate. It cannot add a candidate that failed
Phase 61 and cannot compare/rank candidates. It only confirms or rejects each
already-eligible fixed reference against the final 10 chronological markets
under BOTH base and high illustrative friction.

Passing means eligible for a separate Kalshi DEMO execution design review only.
It does not authorize demo or live order submission.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Mapping

from .kalshi_historical_candidate_gate import (
    CANDIDATES,
    MAX_BLOCKED_FRACTION,
    REQUIRED_SCENARIOS,
)

POLICY_VERSION="kalshi-untouched-confirmation-v1-predeclared-20260930"
MIN_UNTOUCHED_CONTRACTS=3


def _money(raw:object)->Decimal:
    try:
        value=Decimal(str(raw))
    except (InvalidOperation,ValueError,TypeError) as exc:
        raise ValueError("invalid Kalshi untouched-test P&L") from exc
    if not value.is_finite():
        raise ValueError("non-finite Kalshi untouched-test P&L")
    return value


def _count(raw:object, *, name:str)->int:
    if type(raw) is not int or raw<0:
        raise ValueError(f"invalid Kalshi {name}")
    return raw


def confirm_kalshi_untouched_candidates(
    historical_gate:Mapping[str,object],
    chronological:Mapping[str,object],
)->dict[str,object]:
    if (
        historical_gate.get("kind")
        !="KALSHI_PREDECLARED_HISTORICAL_CANDIDATE_GATE_NO_ORDER"
        or historical_gate.get("candidate_ranking_performed") is not False
        or historical_gate.get("automatic_candidate_selection")!="DISABLED"
        or historical_gate.get("untouched_test_accessed_for_candidate_selection") is not False
        or historical_gate.get("demo_execution_eligible") is not False
        or historical_gate.get("live_execution_eligible") is not False
        or historical_gate.get("order_submission")!="DISABLED"
    ):
        raise ValueError("invalid upstream Kalshi historical candidate gate")
    if (
        chronological.get("kind")
        !="OFFLINE_KALSHI_CHRONOLOGICAL_THREE_WAY_RESEARCH"
        or chronological.get("resolved_market_count")!=50
        or chronological.get("untouched_test_used_for_strategy_selection") is not False
        or chronological.get("strategy_ranking_performed") is not False
        or chronological.get("strategy_selection_performed") is not False
        or chronological.get("demo_order_submission")!="DISABLED"
        or chronological.get("live_order_submission")!="DISABLED"
    ):
        raise ValueError("invalid Kalshi chronological research contract")

    upstream=historical_gate.get("candidates_meeting_all_criteria")
    if not isinstance(upstream,list) or any(x not in CANDIDATES for x in upstream):
        raise ValueError("invalid upstream Kalshi candidate list")
    if len(set(upstream))!=len(upstream):
        raise ValueError("duplicate upstream Kalshi candidate")

    scenarios=chronological.get("friction_scenarios")
    if not isinstance(scenarios,Mapping):
        raise ValueError("Kalshi chronological report lacks friction scenarios")

    assessments={}
    confirmed=[]
    for candidate in upstream:
        scenario_results={}
        for scenario in REQUIRED_SCENARIOS:
            scenario_obj=scenarios.get(scenario)
            if not isinstance(scenario_obj,Mapping):
                raise ValueError("Kalshi chronological report lacks required scenario")
            hypotheses=scenario_obj.get("hypotheses")
            if not isinstance(hypotheses,Mapping):
                raise ValueError("Kalshi chronological report lacks hypotheses")
            folds=hypotheses.get(candidate)
            if not isinstance(folds,Mapping):
                raise ValueError("Kalshi chronological report lacks upstream candidate")
            untouched=folds.get("untouched_test")
            if not isinstance(untouched,Mapping):
                raise ValueError("Kalshi chronological report lacks untouched test")

            markets=_count(
                untouched.get("market_count"),
                name="untouched market count",
            )
            contracts=_count(
                untouched.get("hypothetical_contract_count"),
                name="untouched contract count",
            )
            blocked=_count(
                untouched.get("entry_blocked_market_count"),
                name="untouched blocked count",
            )
            pnl=_money(untouched.get("total_hypothetical_pnl_dollars"))
            if markets!=10 or blocked>markets:
                raise ValueError("Kalshi untouched test must contain exact final ten markets")
            blocked_fraction=Decimal(blocked)/Decimal(markets)
            checks={
                "minimum_untouched_activity":{
                    "required_contracts":MIN_UNTOUCHED_CONTRACTS,
                    "observed_contracts":contracts,
                    "pass":contracts>=MIN_UNTOUCHED_CONTRACTS,
                },
                "positive_untouched_pnl":{
                    "observed_pnl_dollars":str(pnl),
                    "pass":pnl>0,
                },
                "untouched_blocked_fraction":{
                    "maximum":str(MAX_BLOCKED_FRACTION),
                    "observed":str(blocked_fraction),
                    "pass":blocked_fraction<=MAX_BLOCKED_FRACTION,
                },
            }
            scenario_results[scenario]={
                "checks":checks,
                "pass":all(item["pass"] for item in checks.values()),
            }
        passes=all(x["pass"] for x in scenario_results.values())
        assessments[candidate]={
            "scenarios":scenario_results,
            "confirmed_on_predeclared_untouched_test":passes,
        }
        if passes:
            confirmed.append(candidate)

    rejected=[x for x in upstream if x not in confirmed]
    return {
        "kind":"KALSHI_UNTOUCHED_TEST_CONFIRMATION_NO_ORDER",
        "policy_version":POLICY_VERSION,
        "upstream_candidates":list(upstream),
        "assessments":assessments,
        "candidates_confirmed_on_untouched_test":confirmed,
        "candidates_rejected_on_untouched_test":rejected,
        "candidate_added_by_untouched_test":False,
        "candidate_ranking_performed":False,
        "automatic_candidate_selection":"DISABLED",
        "historical_confirmation_is_not_prospective_validation":True,
        "next_action":(
            "OWNER_DEMO_EXECUTION_DESIGN_REVIEW_REQUIRED"
            if confirmed else
            "NO_KALSHI_REFERENCE_SURVIVES_FROZEN_HISTORICAL_CONFIRMATION"
        ),
        "eligible_for_demo_execution_design_review":bool(confirmed),
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "separate_owner_authorization_required_for_any_demo_execution":True,
        "live_trading":"UNAVAILABLE",
    }

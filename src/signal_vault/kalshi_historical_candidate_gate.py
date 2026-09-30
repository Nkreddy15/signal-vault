"""Frozen Kalshi historical candidate gate, declared before strategy results.

This gate assesses each non-cash Phase 57 reference independently. It never
ranks candidates and it deliberately ignores the untouched-test fold when
deciding historical candidate eligibility.

A candidate must show enough hypothetical activity and positive historical P&L
under BOTH base and high illustrative entry-friction scenarios on:
1. chronological development and validation folds; and
2. the three later expanding walk-forward blocks.

Passing this gate means only that a fixed reference is eligible for a separate
untouched-test confirmation. It does not authorize Kalshi demo or live orders.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Mapping

POLICY_VERSION="kalshi-historical-candidate-gate-v1-predeclared-20260930"

CANDIDATES=(
    "market-favorite-24h-hold-v1-predeclared",
    "market-favorite-6h-hold-v1-predeclared",
    "market-contrarian-6h-hold-v1-predeclared",
)
REQUIRED_SCENARIOS=(
    "illustrative_base_extra_entry_friction",
    "illustrative_high_extra_entry_friction",
)

MIN_DEVELOPMENT_CONTRACTS=8
MIN_VALIDATION_CONTRACTS=3
MAX_BLOCKED_FRACTION=Decimal("0.20")
MIN_WALK_FORWARD_TOTAL_CONTRACTS=6
MIN_POSITIVE_WALK_FORWARD_FOLDS=2


def _money(raw:object)->Decimal:
    try:
        value=Decimal(str(raw))
    except (InvalidOperation,ValueError,TypeError) as exc:
        raise ValueError("invalid Kalshi historical P&L") from exc
    if not value.is_finite():
        raise ValueError("non-finite Kalshi historical P&L")
    return value


def _count(raw:object, *, name:str)->int:
    if type(raw) is not int or raw<0:
        raise ValueError(f"invalid Kalshi {name}")
    return raw


def _blocked_ok(fold:Mapping[str,object])->tuple[bool,str]:
    markets=_count(fold.get("market_count"),name="fold market count")
    blocked=_count(
        fold.get("entry_blocked_market_count"),
        name="blocked market count",
    )
    if markets<=0 or blocked>markets:
        raise ValueError("inconsistent Kalshi fold blocked count")
    fraction=Decimal(blocked)/Decimal(markets)
    return fraction<=MAX_BLOCKED_FRACTION,str(fraction)


def _chronological_checks(
    report:Mapping[str,object],
    *,
    candidate:str,
    scenario:str,
)->dict[str,object]:
    scenarios=report.get("friction_scenarios")
    if not isinstance(scenarios,Mapping):
        raise ValueError("Kalshi chronological report lacks friction scenarios")
    scenario_obj=scenarios.get(scenario)
    if not isinstance(scenario_obj,Mapping):
        raise ValueError("Kalshi chronological report lacks required scenario")
    hypotheses=scenario_obj.get("hypotheses")
    if not isinstance(hypotheses,Mapping):
        raise ValueError("Kalshi chronological report lacks hypotheses")
    folds=hypotheses.get(candidate)
    if not isinstance(folds,Mapping):
        raise ValueError("Kalshi chronological report lacks fixed candidate")

    development=folds.get("development")
    validation=folds.get("validation")
    if not isinstance(development,Mapping) or not isinstance(validation,Mapping):
        raise ValueError("Kalshi chronological report lacks development/validation folds")

    dev_contracts=_count(
        development.get("hypothetical_contract_count"),
        name="development contract count",
    )
    val_contracts=_count(
        validation.get("hypothetical_contract_count"),
        name="validation contract count",
    )
    dev_pnl=_money(development.get("total_hypothetical_pnl_dollars"))
    val_pnl=_money(validation.get("total_hypothetical_pnl_dollars"))
    dev_blocked_ok,dev_blocked_fraction=_blocked_ok(development)
    val_blocked_ok,val_blocked_fraction=_blocked_ok(validation)

    checks={
        "development_minimum_activity":{
            "required_contracts":MIN_DEVELOPMENT_CONTRACTS,
            "observed_contracts":dev_contracts,
            "pass":dev_contracts>=MIN_DEVELOPMENT_CONTRACTS,
        },
        "validation_minimum_activity":{
            "required_contracts":MIN_VALIDATION_CONTRACTS,
            "observed_contracts":val_contracts,
            "pass":val_contracts>=MIN_VALIDATION_CONTRACTS,
        },
        "development_positive_pnl":{
            "observed_pnl_dollars":str(dev_pnl),
            "pass":dev_pnl>0,
        },
        "validation_positive_pnl":{
            "observed_pnl_dollars":str(val_pnl),
            "pass":val_pnl>0,
        },
        "development_blocked_fraction":{
            "maximum":str(MAX_BLOCKED_FRACTION),
            "observed":dev_blocked_fraction,
            "pass":dev_blocked_ok,
        },
        "validation_blocked_fraction":{
            "maximum":str(MAX_BLOCKED_FRACTION),
            "observed":val_blocked_fraction,
            "pass":val_blocked_ok,
        },
    }
    return {
        "checks":checks,
        "pass":all(item["pass"] for item in checks.values()),
        "untouched_test_accessed_for_candidate_selection":False,
    }


def _walk_forward_checks(
    report:Mapping[str,object],
    *,
    candidate:str,
    scenario:str,
)->dict[str,object]:
    scenarios=report.get("friction_scenarios")
    if not isinstance(scenarios,Mapping):
        raise ValueError("Kalshi walk-forward report lacks friction scenarios")
    scenario_obj=scenarios.get(scenario)
    if not isinstance(scenario_obj,Mapping):
        raise ValueError("Kalshi walk-forward report lacks required scenario")
    hypotheses=scenario_obj.get("hypotheses")
    if not isinstance(hypotheses,Mapping):
        raise ValueError("Kalshi walk-forward report lacks hypotheses")
    result=hypotheses.get(candidate)
    if not isinstance(result,Mapping):
        raise ValueError("Kalshi walk-forward report lacks fixed candidate")
    if (
        result.get("strategy_selected_from_fold_results") is not False
        or result.get("thresholds_changed_from_fold_results") is not False
    ):
        raise ValueError("Kalshi walk-forward candidate was modified from fold results")
    folds=result.get("folds")
    if not isinstance(folds,list) or len(folds)!=3:
        raise ValueError("Kalshi candidate gate requires exactly three walk-forward folds")

    total_pnl=Decimal(0)
    total_contracts=0
    positive_folds=0
    for expected,fold in enumerate(folds,1):
        if not isinstance(fold,Mapping) or fold.get("fold")!=expected:
            raise ValueError("Kalshi walk-forward fold sequence invalid")
        pnl=_money(fold.get("total_hypothetical_pnl_dollars"))
        contracts=_count(
            fold.get("hypothetical_contract_count"),
            name="walk-forward contract count",
        )
        total_pnl+=pnl
        total_contracts+=contracts
        positive_folds+=int(pnl>0)

    checks={
        "walk_forward_total_positive_pnl":{
            "observed_pnl_dollars":str(total_pnl),
            "pass":total_pnl>0,
        },
        "walk_forward_minimum_activity":{
            "required_contracts":MIN_WALK_FORWARD_TOTAL_CONTRACTS,
            "observed_contracts":total_contracts,
            "pass":total_contracts>=MIN_WALK_FORWARD_TOTAL_CONTRACTS,
        },
        "walk_forward_positive_fold_count":{
            "required_positive_folds":MIN_POSITIVE_WALK_FORWARD_FOLDS,
            "observed_positive_folds":positive_folds,
            "total_folds":3,
            "pass":positive_folds>=MIN_POSITIVE_WALK_FORWARD_FOLDS,
        },
    }
    return {
        "checks":checks,
        "pass":all(item["pass"] for item in checks.values()),
        "fold_results_used_to_modify_strategy":False,
    }


def assess_kalshi_historical_candidates(
    chronological:Mapping[str,object],
    walk_forward:Mapping[str,object],
)->dict[str,object]:
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
    if (
        walk_forward.get("kind")
        !="OFFLINE_KALSHI_EXPANDING_WALK_FORWARD_RESEARCH"
        or walk_forward.get("resolved_market_count")!=50
        or walk_forward.get("fold_count")!=3
        or walk_forward.get("fold_results_used_to_modify_strategy") is not False
        or walk_forward.get("strategy_ranking_performed") is not False
        or walk_forward.get("strategy_selection_performed") is not False
        or walk_forward.get("demo_order_submission")!="DISABLED"
        or walk_forward.get("live_order_submission")!="DISABLED"
    ):
        raise ValueError("invalid Kalshi walk-forward research contract")

    assessments={}
    eligible=[]
    for candidate in CANDIDATES:
        scenario_results={}
        for scenario in REQUIRED_SCENARIOS:
            chronological_result=_chronological_checks(
                chronological,candidate=candidate,scenario=scenario
            )
            walk_result=_walk_forward_checks(
                walk_forward,candidate=candidate,scenario=scenario
            )
            scenario_results[scenario]={
                "chronological_development_validation":chronological_result,
                "expanding_walk_forward":walk_result,
                "pass":chronological_result["pass"] and walk_result["pass"],
            }
        candidate_pass=all(x["pass"] for x in scenario_results.values())
        assessments[candidate]={
            "scenarios":scenario_results,
            "meets_all_predeclared_historical_candidate_criteria":
                candidate_pass,
        }
        if candidate_pass:
            eligible.append(candidate)

    return {
        "kind":"KALSHI_PREDECLARED_HISTORICAL_CANDIDATE_GATE_NO_ORDER",
        "policy_version":POLICY_VERSION,
        "candidates_assessed_independently":list(CANDIDATES),
        "required_friction_scenarios":list(REQUIRED_SCENARIOS),
        "criteria":{
            "minimum_development_contracts":MIN_DEVELOPMENT_CONTRACTS,
            "minimum_validation_contracts":MIN_VALIDATION_CONTRACTS,
            "maximum_blocked_fraction":str(MAX_BLOCKED_FRACTION),
            "minimum_walk_forward_total_contracts":
                MIN_WALK_FORWARD_TOTAL_CONTRACTS,
            "minimum_positive_walk_forward_folds":
                MIN_POSITIVE_WALK_FORWARD_FOLDS,
            "positive_development_validation_pnl_required_under_each_scenario":
                True,
            "positive_total_walk_forward_pnl_required_under_each_scenario":
                True,
        },
        "assessments":assessments,
        "candidates_meeting_all_criteria":eligible,
        "candidate_ranking_performed":False,
        "automatic_candidate_selection":"DISABLED",
        "untouched_test_accessed_for_candidate_selection":False,
        "next_action":(
            "RUN_UNTOUCHED_TEST_CONFIRMATION_BEFORE_ANY_DEMO_DESIGN"
            if eligible else
            "NO_HISTORICAL_CANDIDATE_MEETS_FROZEN_DEV_VALIDATION_GATE"
        ),
        "demo_execution_eligible":False,
        "live_execution_eligible":False,
        "separate_owner_authorization_required_for_any_demo_execution":True,
        "order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }

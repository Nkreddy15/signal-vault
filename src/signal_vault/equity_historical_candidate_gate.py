"""Predeclared US-equity historical candidate gate, no orders.

This policy is frozen before long-horizon stock results are used for strategy
eligibility. Cash and passive allocation remain controls; only the predeclared
EMA and momentum rules are active candidates.

Each candidate is assessed independently under base and high illustrative
equity friction. Development and validation must be positive, beat the passive
shared-$100 benchmark, show enough activity, stay within the shared drawdown
cap, and avoid the persistent peak-drawdown halt. Expanding walk-forward must
also be positive overall, beat passive overall, and outperform passive in a
strict majority of folds.

The untouched-test fold is never accessed for candidate selection.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Mapping

POLICY_VERSION="equity-historical-candidate-gate-v1-predeclared-20260930"

CANDIDATES=(
    "generic-ema12x26-v1-predeclared",
    "generic-momentum24bar50bps-v1-predeclared",
)
PASSIVE="one-allocation-passive-v1-predeclared"
REQUIRED_SCENARIOS=(
    "illustrative_base_equity_friction",
    "illustrative_high_equity_friction",
)
MIN_DEVELOPMENT_FILLS=6
MIN_VALIDATION_FILLS=2
MIN_WALK_FORWARD_FILLS=10
MAX_SHARED_DRAWDOWN_USD=Decimal("10")


def _money(raw:object, *, name:str)->Decimal:
    try:
        value=Decimal(str(raw))
    except (InvalidOperation,ValueError,TypeError) as exc:
        raise ValueError(f"invalid stock {name}") from exc
    if not value.is_finite():
        raise ValueError(f"non-finite stock {name}")
    return value


def _count(raw:object, *, name:str)->int:
    if type(raw) is not int or raw<0:
        raise ValueError(f"invalid stock {name}")
    return raw


def _three_way_fold(
    report:Mapping[str,object],
    *,
    scenario:str,
    hypothesis:str,
    fold:str,
)->Mapping[str,object]:
    scenarios=report.get("three_fixed_friction_scenarios")
    if not isinstance(scenarios,Mapping):
        raise ValueError("stock shared three-way report lacks scenarios")
    scenario_obj=scenarios.get(scenario)
    if not isinstance(scenario_obj,Mapping):
        raise ValueError("stock shared three-way report lacks required scenario")
    hypotheses=scenario_obj.get("hypotheses")
    if not isinstance(hypotheses,Mapping):
        raise ValueError("stock shared three-way report lacks hypotheses")
    folds=hypotheses.get(hypothesis)
    if not isinstance(folds,Mapping):
        raise ValueError("stock shared three-way report lacks fixed hypothesis")
    item=folds.get(fold)
    if not isinstance(item,Mapping):
        raise ValueError("stock shared three-way report lacks required fold")
    return item


def _fold_checks(
    candidate_fold:Mapping[str,object],
    passive_fold:Mapping[str,object],
    *,
    minimum_fills:int,
)->dict[str,object]:
    candidate_pnl=_money(
        candidate_fold.get("net_pnl_if_hypothetically_liquidated_usd"),
        name="candidate fold P&L",
    )
    passive_pnl=_money(
        passive_fold.get("net_pnl_if_hypothetically_liquidated_usd"),
        name="passive fold P&L",
    )
    fills=_count(
        candidate_fold.get("synthetic_fill_count"),
        name="candidate fold fill count",
    )
    drawdown=_money(
        candidate_fold.get("sampled_event_max_drawdown_usd"),
        name="candidate fold drawdown",
    )
    if drawdown<0:
        raise ValueError("stock drawdown cannot be negative")
    halt=candidate_fold.get("persistent_peak_drawdown_entry_halt")
    if type(halt) is not bool:
        raise ValueError("stock persistent drawdown halt must be boolean")

    checks={
        "minimum_activity":{
            "required_fills":minimum_fills,
            "observed_fills":fills,
            "pass":fills>=minimum_fills,
        },
        "positive_candidate_pnl":{
            "observed_pnl_usd":str(candidate_pnl),
            "pass":candidate_pnl>0,
        },
        "beats_passive_same_fold":{
            "candidate_pnl_usd":str(candidate_pnl),
            "passive_pnl_usd":str(passive_pnl),
            "pass":candidate_pnl>passive_pnl,
        },
        "drawdown_within_shared_cap":{
            "maximum_usd":str(MAX_SHARED_DRAWDOWN_USD),
            "observed_usd":str(drawdown),
            "pass":drawdown<=MAX_SHARED_DRAWDOWN_USD,
        },
        "persistent_peak_drawdown_halt_not_triggered":{
            "observed":halt,
            "pass":not halt,
        },
    }
    return {
        "checks":checks,
        "pass":all(x["pass"] for x in checks.values()),
    }


def _walk_forward_checks(
    report:Mapping[str,object],
    *,
    scenario:str,
    candidate:str,
)->dict[str,object]:
    scenarios=report.get("three_fixed_friction_scenarios")
    if not isinstance(scenarios,Mapping):
        raise ValueError("stock walk-forward report lacks scenarios")
    scenario_obj=scenarios.get(scenario)
    if not isinstance(scenario_obj,Mapping):
        raise ValueError("stock walk-forward report lacks required scenario")
    hypotheses=scenario_obj.get("hypotheses")
    if not isinstance(hypotheses,Mapping):
        raise ValueError("stock walk-forward report lacks hypotheses")
    candidate_obj=hypotheses.get(candidate)
    passive_obj=hypotheses.get(PASSIVE)
    if not isinstance(candidate_obj,Mapping) or not isinstance(passive_obj,Mapping):
        raise ValueError("stock walk-forward lacks candidate/passive hypothesis")
    if (
        candidate_obj.get("strategy_selected_from_fold_results") is not False
        or candidate_obj.get("hyperparameter_tuning_from_fold_results") is not False
        or passive_obj.get("strategy_selected_from_fold_results") is not False
        or passive_obj.get("hyperparameter_tuning_from_fold_results") is not False
    ):
        raise ValueError("stock walk-forward strategy changed from fold results")
    candidate_folds=candidate_obj.get("folds")
    passive_folds=passive_obj.get("folds")
    if (
        not isinstance(candidate_folds,list)
        or not isinstance(passive_folds,list)
        or not candidate_folds
        or len(candidate_folds)!=len(passive_folds)
    ):
        raise ValueError("stock walk-forward fold clocks differ")

    total_candidate=Decimal(0)
    total_passive=Decimal(0)
    total_fills=0
    outperform_count=0
    drawdown_ok=True
    no_halts=True
    fold_receipts=[]
    for expected,(cand,base) in enumerate(
        zip(candidate_folds,passive_folds),1
    ):
        if (
            not isinstance(cand,Mapping)
            or not isinstance(base,Mapping)
            or cand.get("fold")!=expected
            or base.get("fold")!=expected
            or cand.get("validation_start_utc")!=base.get("validation_start_utc")
            or cand.get("validation_end_utc_exclusive")
               !=base.get("validation_end_utc_exclusive")
        ):
            raise ValueError("stock candidate/passive walk-forward clocks differ")
        candidate_pnl=_money(
            cand.get("net_pnl_if_hypothetically_liquidated_usd"),
            name="walk-forward candidate P&L",
        )
        passive_pnl=_money(
            base.get("net_pnl_if_hypothetically_liquidated_usd"),
            name="walk-forward passive P&L",
        )
        fills=_count(
            cand.get("synthetic_fill_count"),
            name="walk-forward fill count",
        )
        drawdown=_money(
            cand.get("sampled_event_max_drawdown_usd"),
            name="walk-forward drawdown",
        )
        halt=cand.get("persistent_peak_drawdown_entry_halt")
        if drawdown<0 or type(halt) is not bool:
            raise ValueError("invalid stock walk-forward risk state")
        total_candidate+=candidate_pnl
        total_passive+=passive_pnl
        total_fills+=fills
        beat=candidate_pnl>passive_pnl
        outperform_count+=int(beat)
        drawdown_ok=drawdown_ok and drawdown<=MAX_SHARED_DRAWDOWN_USD
        no_halts=no_halts and not halt
        fold_receipts.append({
            "fold":expected,
            "candidate_pnl_usd":str(candidate_pnl),
            "passive_pnl_usd":str(passive_pnl),
            "candidate_beats_passive":beat,
            "candidate_fill_count":fills,
            "candidate_drawdown_usd":str(drawdown),
            "persistent_peak_drawdown_halt":halt,
        })

    fold_count=len(candidate_folds)
    strict_majority=outperform_count*2>fold_count
    checks={
        "positive_total_walk_forward_pnl":{
            "observed_candidate_pnl_usd":str(total_candidate),
            "pass":total_candidate>0,
        },
        "beats_passive_total_walk_forward":{
            "candidate_pnl_usd":str(total_candidate),
            "passive_pnl_usd":str(total_passive),
            "pass":total_candidate>total_passive,
        },
        "minimum_walk_forward_activity":{
            "required_fills":MIN_WALK_FORWARD_FILLS,
            "observed_fills":total_fills,
            "pass":total_fills>=MIN_WALK_FORWARD_FILLS,
        },
        "beats_passive_in_strict_majority_of_folds":{
            "fold_count":fold_count,
            "outperforming_fold_count":outperform_count,
            "pass":strict_majority,
        },
        "all_walk_forward_drawdowns_within_shared_cap":{
            "maximum_usd":str(MAX_SHARED_DRAWDOWN_USD),
            "pass":drawdown_ok,
        },
        "no_persistent_peak_drawdown_halt":{
            "pass":no_halts,
        },
    }
    return {
        "folds":fold_receipts,
        "checks":checks,
        "pass":all(x["pass"] for x in checks.values()),
    }


def assess_equity_historical_candidates(
    three_way:Mapping[str,object],
    walk_forward:Mapping[str,object],
)->dict[str,object]:
    if (
        three_way.get("kind")
        !="OFFLINE_SHARED_SIX_STOCK_CHRONOLOGICAL_THREE_WAY_RESEARCH"
        or three_way.get("untouched_test_used_for_strategy_selection") is not False
        or three_way.get("strategy_ranking_performed") is not False
        or three_way.get("strategy_selection_performed") is not False
        or three_way.get("broker_order_submission")!="DISABLED"
        or three_way.get("live_trading")!="UNAVAILABLE"
    ):
        raise ValueError("invalid shared stock three-way research contract")
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
        raise ValueError("invalid stock walk-forward research contract")

    assessments={}
    eligible=[]
    for candidate in CANDIDATES:
        scenario_results={}
        for scenario in REQUIRED_SCENARIOS:
            development=_fold_checks(
                _three_way_fold(
                    three_way,scenario=scenario,
                    hypothesis=candidate,fold="development",
                ),
                _three_way_fold(
                    three_way,scenario=scenario,
                    hypothesis=PASSIVE,fold="development",
                ),
                minimum_fills=MIN_DEVELOPMENT_FILLS,
            )
            validation=_fold_checks(
                _three_way_fold(
                    three_way,scenario=scenario,
                    hypothesis=candidate,fold="validation",
                ),
                _three_way_fold(
                    three_way,scenario=scenario,
                    hypothesis=PASSIVE,fold="validation",
                ),
                minimum_fills=MIN_VALIDATION_FILLS,
            )
            walk=_walk_forward_checks(
                walk_forward,scenario=scenario,candidate=candidate
            )
            scenario_pass=(
                development["pass"]
                and validation["pass"]
                and walk["pass"]
            )
            scenario_results[scenario]={
                "development":development,
                "validation":validation,
                "expanding_walk_forward":walk,
                "pass":scenario_pass,
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
        "kind":"EQUITY_PREDECLARED_HISTORICAL_CANDIDATE_GATE_NO_ORDER",
        "policy_version":POLICY_VERSION,
        "active_candidates_assessed_independently":list(CANDIDATES),
        "passive_benchmark":PASSIVE,
        "required_friction_scenarios":list(REQUIRED_SCENARIOS),
        "criteria":{
            "minimum_development_fills":MIN_DEVELOPMENT_FILLS,
            "minimum_validation_fills":MIN_VALIDATION_FILLS,
            "minimum_walk_forward_fills":MIN_WALK_FORWARD_FILLS,
            "maximum_shared_drawdown_usd":
                str(MAX_SHARED_DRAWDOWN_USD),
            "positive_development_and_validation_pnl_required":True,
            "must_beat_passive_in_development_and_validation":True,
            "must_beat_passive_total_walk_forward":True,
            "must_beat_passive_in_strict_majority_walk_forward_folds":True,
            "persistent_peak_drawdown_halt_allowed":False,
        },
        "assessments":assessments,
        "candidates_meeting_all_criteria":eligible,
        "candidate_ranking_performed":False,
        "automatic_candidate_selection":"DISABLED",
        "untouched_test_accessed_for_candidate_selection":False,
        "next_action":(
            "RUN_STOCK_UNTOUCHED_TEST_CONFIRMATION"
            if eligible else
            "NO_ACTIVE_STOCK_REFERENCE_MEETS_FROZEN_HISTORICAL_GATE"
        ),
        "paper_execution_eligible":False,
        "live_execution_eligible":False,
        "broker_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }

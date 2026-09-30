"""Untouched-test confirmation for already-eligible US-equity candidates.

This stage is downstream of the frozen Phase 68 development/validation gate.
It cannot add or rank a candidate. It only confirms/rejects each already
eligible EMA/momentum reference on the final shared-bankroll stock fold under
both base and high friction, against the same passive benchmark.

Passing means eligible for a separate PAPER execution design review only.
It never authorizes paper or live order submission.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Mapping

from .equity_historical_candidate_gate import (
    CANDIDATES,
    MAX_SHARED_DRAWDOWN_USD,
    PASSIVE,
    REQUIRED_SCENARIOS,
)

POLICY_VERSION="equity-untouched-confirmation-v1-predeclared-20260930"
MIN_UNTOUCHED_FILLS=2


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


def _fold(
    report:Mapping[str,object],
    *,
    scenario:str,
    hypothesis:str,
)->Mapping[str,object]:
    scenarios=report.get("three_fixed_friction_scenarios")
    if not isinstance(scenarios,Mapping):
        raise ValueError("stock three-way report lacks scenarios")
    scenario_obj=scenarios.get(scenario)
    if not isinstance(scenario_obj,Mapping):
        raise ValueError("stock three-way report lacks required scenario")
    hypotheses=scenario_obj.get("hypotheses")
    if not isinstance(hypotheses,Mapping):
        raise ValueError("stock three-way report lacks hypotheses")
    folds=hypotheses.get(hypothesis)
    if not isinstance(folds,Mapping):
        raise ValueError("stock three-way report lacks fixed hypothesis")
    item=folds.get("untouched_test")
    if not isinstance(item,Mapping):
        raise ValueError("stock three-way report lacks untouched fold")
    return item


def confirm_equity_untouched_candidates(
    historical_gate:Mapping[str,object],
    three_way:Mapping[str,object],
)->dict[str,object]:
    if (
        historical_gate.get("kind")
        !="EQUITY_PREDECLARED_HISTORICAL_CANDIDATE_GATE_NO_ORDER"
        or historical_gate.get("candidate_ranking_performed") is not False
        or historical_gate.get("automatic_candidate_selection")!="DISABLED"
        or historical_gate.get("untouched_test_accessed_for_candidate_selection") is not False
        or historical_gate.get("paper_execution_eligible") is not False
        or historical_gate.get("live_execution_eligible") is not False
        or historical_gate.get("broker_order_submission")!="DISABLED"
    ):
        raise ValueError("invalid upstream stock historical candidate gate")
    if (
        three_way.get("kind")
        !="OFFLINE_SHARED_SIX_STOCK_CHRONOLOGICAL_THREE_WAY_RESEARCH"
        or three_way.get("untouched_test_used_for_strategy_selection") is not False
        or three_way.get("strategy_ranking_performed") is not False
        or three_way.get("strategy_selection_performed") is not False
        or three_way.get("broker_order_submission")!="DISABLED"
        or three_way.get("live_trading")!="UNAVAILABLE"
    ):
        raise ValueError("invalid stock three-way research contract")

    upstream=historical_gate.get("candidates_meeting_all_criteria")
    if (
        not isinstance(upstream,list)
        or any(x not in CANDIDATES for x in upstream)
        or len(set(upstream))!=len(upstream)
    ):
        raise ValueError("invalid upstream stock candidate list")

    assessments={}
    confirmed=[]
    for candidate in upstream:
        scenario_results={}
        for scenario in REQUIRED_SCENARIOS:
            candidate_fold=_fold(
                three_way,scenario=scenario,hypothesis=candidate
            )
            passive_fold=_fold(
                three_way,scenario=scenario,hypothesis=PASSIVE
            )
            candidate_pnl=_money(
                candidate_fold.get(
                    "net_pnl_if_hypothetically_liquidated_usd"
                ),
                name="untouched candidate P&L",
            )
            passive_pnl=_money(
                passive_fold.get(
                    "net_pnl_if_hypothetically_liquidated_usd"
                ),
                name="untouched passive P&L",
            )
            fills=_count(
                candidate_fold.get("synthetic_fill_count"),
                name="untouched fill count",
            )
            drawdown=_money(
                candidate_fold.get("sampled_event_max_drawdown_usd"),
                name="untouched drawdown",
            )
            halt=candidate_fold.get("persistent_peak_drawdown_entry_halt")
            if drawdown<0 or type(halt) is not bool:
                raise ValueError("invalid stock untouched risk state")
            checks={
                "minimum_untouched_activity":{
                    "required_fills":MIN_UNTOUCHED_FILLS,
                    "observed_fills":fills,
                    "pass":fills>=MIN_UNTOUCHED_FILLS,
                },
                "positive_untouched_pnl":{
                    "observed_pnl_usd":str(candidate_pnl),
                    "pass":candidate_pnl>0,
                },
                "beats_passive_on_untouched_fold":{
                    "candidate_pnl_usd":str(candidate_pnl),
                    "passive_pnl_usd":str(passive_pnl),
                    "pass":candidate_pnl>passive_pnl,
                },
                "untouched_drawdown_within_shared_cap":{
                    "maximum_usd":str(MAX_SHARED_DRAWDOWN_USD),
                    "observed_usd":str(drawdown),
                    "pass":drawdown<=MAX_SHARED_DRAWDOWN_USD,
                },
                "persistent_peak_drawdown_halt_not_triggered":{
                    "observed":halt,
                    "pass":not halt,
                },
            }
            scenario_results[scenario]={
                "checks":checks,
                "pass":all(x["pass"] for x in checks.values()),
            }
        passed=all(x["pass"] for x in scenario_results.values())
        assessments[candidate]={
            "scenarios":scenario_results,
            "confirmed_on_predeclared_untouched_test":passed,
        }
        if passed:
            confirmed.append(candidate)

    rejected=[x for x in upstream if x not in confirmed]
    return {
        "kind":"EQUITY_UNTOUCHED_TEST_CONFIRMATION_NO_ORDER",
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
            "START_PROSPECTIVE_STOCK_SHADOW_COLLECTION"
            if confirmed else
            "NO_ACTIVE_STOCK_REFERENCE_SURVIVES_FROZEN_HISTORICAL_CONFIRMATION"
        ),
        "eligible_for_paper_execution_design_review":False,
        "paper_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "separate_owner_authorization_required_for_any_paper_execution":True,
        "live_trading":"UNAVAILABLE",
    }

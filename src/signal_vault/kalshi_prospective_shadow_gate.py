"""Predeclared prospective Kalshi shadow gate, no orders.

Event contracts are validated by independent future markets, not by an arbitrary
hour count. This gate is frozen before any prospective outcomes are observed.

Only candidates already confirmed by the Phase 62 untouched-test gate may be
assessed. The future collector must precommit market selection and candidate
versions before settlement, never backfill missed outcomes, and record two
chronological ten-market blocks. Each candidate is assessed independently under
base and high illustrative friction; no candidate is ranked or automatically
selected.

Passing means prospective/shadow evidence is complete for a fixed candidate.
It still does not authorize DEMO or LIVE order submission.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Mapping

from .kalshi_historical_candidate_gate import REQUIRED_SCENARIOS

POLICY_VERSION="kalshi-prospective-shadow-gate-v1-predeclared-20260930"
EXPECTED_HYPOTHESIS_POLICY="kalshi-reference-hypotheses-v1-predeclared-20260930"
MIN_VALID_PROSPECTIVE_MARKETS=20
MIN_DISTINCT_EVENTS=10
MIN_CAPTURE_COVERAGE=Decimal("0.90")
REQUIRED_BLOCKS=2
MARKETS_PER_BLOCK=10
MIN_CANDIDATE_CONTRACTS=10


def _count(raw:object, *, name:str)->int:
    if type(raw) is not int or raw<0:
        raise ValueError(f"invalid Kalshi prospective {name}")
    return raw


def _money(raw:object)->Decimal:
    try:
        value=Decimal(str(raw))
    except (InvalidOperation,ValueError,TypeError) as exc:
        raise ValueError("invalid Kalshi prospective shadow P&L") from exc
    if not value.is_finite():
        raise ValueError("non-finite Kalshi prospective shadow P&L")
    return value


def _fraction(raw:object)->Decimal:
    try:
        value=Decimal(str(raw))
    except (InvalidOperation,ValueError,TypeError) as exc:
        raise ValueError("invalid Kalshi prospective capture coverage") from exc
    if not value.is_finite() or value<0 or value>1:
        raise ValueError("Kalshi prospective capture coverage outside 0..1")
    return value


def assess_kalshi_prospective_shadow(
    untouched_confirmation:Mapping[str,object],
    summary:Mapping[str,object],
)->dict[str,object]:
    if (
        untouched_confirmation.get("kind")
        !="KALSHI_UNTOUCHED_TEST_CONFIRMATION_NO_ORDER"
        or untouched_confirmation.get("candidate_added_by_untouched_test") is not False
        or untouched_confirmation.get("candidate_ranking_performed") is not False
        or untouched_confirmation.get("automatic_candidate_selection")!="DISABLED"
        or untouched_confirmation.get("demo_order_submission")!="DISABLED"
        or untouched_confirmation.get("live_order_submission")!="DISABLED"
    ):
        raise ValueError("invalid Kalshi historical confirmation receipt")

    confirmed=untouched_confirmation.get(
        "candidates_confirmed_on_untouched_test"
    )
    if (
        not isinstance(confirmed,list)
        or any(not isinstance(x,str) or not x for x in confirmed)
        or len(set(confirmed))!=len(confirmed)
    ):
        raise ValueError("invalid historically confirmed Kalshi candidate list")

    if summary.get("kind")!="KALSHI_PROSPECTIVE_SHADOW_SUMMARY_NO_ORDERS":
        raise ValueError("unexpected Kalshi prospective shadow summary")
    if (
        summary.get("hypothesis_policy_version")!=EXPECTED_HYPOTHESIS_POLICY
        or summary.get("candidate_versions_changed_after_start") is not False
        or summary.get("outcome_direction_used_for_market_selection") is not False
        or summary.get("historical_backfill_count")!=0
        or summary.get("post_settlement_decision_count")!=0
        or summary.get("source_integrity_passed") is not True
        or summary.get("network_methods")!=["GET"]
        or summary.get("demo_order_submission")!="DISABLED"
        or summary.get("live_order_submission")!="DISABLED"
    ):
        raise ValueError("Kalshi prospective shadow escaped precommitted GET-only contract")

    planned=_count(
        summary.get("planned_market_count"),name="planned market count"
    )
    valid=_count(
        summary.get("valid_prospective_market_count"),
        name="valid market count",
    )
    events=_count(
        summary.get("distinct_event_count"),name="distinct event count"
    )
    missed=_count(
        summary.get("missed_or_invalid_market_count"),
        name="missed/invalid market count",
    )
    if planned<=0 or valid+missed!=planned or valid>planned:
        raise ValueError("Kalshi prospective plan/capture counts inconsistent")
    coverage=_fraction(summary.get("capture_coverage_fraction"))
    exact=Decimal(valid)/Decimal(planned)
    if coverage!=exact:
        raise ValueError("Kalshi prospective capture coverage does not match counts")

    global_checks={
        "minimum_valid_prospective_markets":{
            "required":MIN_VALID_PROSPECTIVE_MARKETS,
            "observed":valid,
            "pass":valid>=MIN_VALID_PROSPECTIVE_MARKETS,
        },
        "minimum_distinct_events":{
            "required":MIN_DISTINCT_EVENTS,
            "observed":events,
            "pass":events>=MIN_DISTINCT_EVENTS,
        },
        "minimum_capture_coverage":{
            "required":str(MIN_CAPTURE_COVERAGE),
            "observed":str(coverage),
            "pass":coverage>=MIN_CAPTURE_COVERAGE,
        },
        "no_backfill_or_post_settlement_decisions":{
            "historical_backfill_count":0,
            "post_settlement_decision_count":0,
            "pass":True,
        },
    }
    global_pass=all(x["pass"] for x in global_checks.values())

    candidates=summary.get("candidate_results")
    if not isinstance(candidates,Mapping):
        raise ValueError("Kalshi prospective summary lacks candidate results")
    if any(name not in confirmed for name in candidates):
        raise ValueError("prospective summary contains candidate not historically confirmed")
    missing=[name for name in confirmed if name not in candidates]
    if missing:
        raise ValueError("historically confirmed candidate missing prospective result")

    assessments={}
    passed=[]
    for candidate in confirmed:
        candidate_obj=candidates[candidate]
        if not isinstance(candidate_obj,Mapping):
            raise ValueError("malformed Kalshi prospective candidate result")
        scenario_results={}
        for scenario in REQUIRED_SCENARIOS:
            scenario_obj=candidate_obj.get(scenario)
            if not isinstance(scenario_obj,Mapping):
                raise ValueError("Kalshi prospective candidate missing required friction scenario")
            contracts=_count(
                scenario_obj.get("hypothetical_contract_count"),
                name="candidate contract count",
            )
            total_pnl=_money(
                scenario_obj.get("total_hypothetical_pnl_dollars")
            )
            blocks=scenario_obj.get("chronological_blocks")
            if not isinstance(blocks,list) or len(blocks)!=REQUIRED_BLOCKS:
                raise ValueError("Kalshi prospective candidate requires two fixed blocks")
            block_checks=[]
            for expected,block in enumerate(blocks,1):
                if (
                    not isinstance(block,Mapping)
                    or block.get("block")!=expected
                    or block.get("market_count")!=MARKETS_PER_BLOCK
                ):
                    raise ValueError("Kalshi prospective fixed block contract mismatch")
                block_pnl=_money(
                    block.get("total_hypothetical_pnl_dollars")
                )
                block_checks.append({
                    "block":expected,
                    "observed_pnl_dollars":str(block_pnl),
                    "pass":block_pnl>0,
                })
            checks={
                "minimum_candidate_activity":{
                    "required_contracts":MIN_CANDIDATE_CONTRACTS,
                    "observed_contracts":contracts,
                    "pass":contracts>=MIN_CANDIDATE_CONTRACTS,
                },
                "positive_total_shadow_pnl":{
                    "observed_pnl_dollars":str(total_pnl),
                    "pass":total_pnl>0,
                },
                "both_chronological_blocks_positive":{
                    "blocks":block_checks,
                    "pass":all(x["pass"] for x in block_checks),
                },
            }
            scenario_results[scenario]={
                "checks":checks,
                "pass":all(x["pass"] for x in checks.values()),
            }
        candidate_pass=global_pass and all(
            x["pass"] for x in scenario_results.values()
        )
        assessments[candidate]={
            "scenarios":scenario_results,
            "prospective_shadow_complete":candidate_pass,
        }
        if candidate_pass:
            passed.append(candidate)

    return {
        "kind":"KALSHI_PROSPECTIVE_SHADOW_GATE_NO_ORDER",
        "policy_version":POLICY_VERSION,
        "global_checks":global_checks,
        "historically_confirmed_candidates":list(confirmed),
        "assessments":assessments,
        "candidates_passing_prospective_shadow":passed,
        "candidate_added_by_prospective_results":False,
        "candidate_ranking_performed":False,
        "automatic_candidate_selection":"DISABLED",
        "prospective_or_shadow_complete":bool(passed),
        "historical_data_substituted_for_prospective_evidence":False,
        "next_action":(
            "DEMO_EXECUTION_VALIDATION_AND_OWNER_REVIEW_REMAIN_REQUIRED"
            if passed else
            "CONTINUE_PROSPECTIVE_SHADOW_COLLECTION"
        ),
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "owner_live_authorization_recorded":False,
        "live_trading":"UNAVAILABLE",
    }

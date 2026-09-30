"""Predeclared prospective review gate for six-crypto shadow candidates.

Frozen BEFORE the first genuine six-crypto prospective hour is scored.
This gate cannot place or enable an order. Passing only means an ACTIVE
hypothesis may be discussed for a separate owner-authorized PAPER execution
design review after source/shadow integrity, costs, venue constraints and
account reconciliation are independently checked.

The criteria intentionally reuse conservative ideas from the older
ResearchGatePolicy instead of tuning thresholds on future sidecar outcomes:
- 169 prospective source hours -> 168 fully observed precommitted outcomes.
- >=10 synthetic fills in the base-friction forward replay.
- positive exit-inclusive P&L under BOTH base and high friction.
- outperform the fixed passive comparator under BOTH base and high friction.
- sampled drawdown <= the existing $10 logical-account review limit.
- no persistent peak-drawdown halt in base/high scenarios.

Cash/passive remain comparators and are NEVER promoted by this gate.
No candidate is ranked; each either meets all frozen review criteria or not.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping

from .multi_asset_simulation import HYPOTHESES, HypothesisKind

POLICY_VERSION="six-crypto-forward-review-gate-v1-predeclared-20260930"
MIN_SOURCE_HOURS=169
MIN_SCORED_OUTCOMES=168
MIN_BASE_FILLS=10
MAX_DRAWDOWN_USD=Decimal("10")
BASE_SCENARIO="illustrative_base_friction"
HIGH_SCENARIO="illustrative_high_friction"


@dataclass(frozen=True)
class ForwardReviewPolicy:
    policy_version:str=POLICY_VERSION
    minimum_prospective_source_hours:int=MIN_SOURCE_HOURS
    minimum_fully_scored_outcomes:int=MIN_SCORED_OUTCOMES
    minimum_base_synthetic_fills:int=MIN_BASE_FILLS
    maximum_sampled_drawdown_usd:Decimal=MAX_DRAWDOWN_USD

    def __post_init__(self) -> None:
        if (self.policy_version!=POLICY_VERSION or
                self.minimum_prospective_source_hours!=169 or
                self.minimum_fully_scored_outcomes!=168 or
                self.minimum_base_synthetic_fills!=10 or
                type(self.maximum_sampled_drawdown_usd) is not Decimal or
                self.maximum_sampled_drawdown_usd!=Decimal("10")):
            raise ValueError("forward review gate v1 thresholds are frozen")


def _money(value:object,name:str) -> Decimal:
    if isinstance(value,bool) or not isinstance(value,(str,int,float,Decimal)):
        raise ValueError("invalid "+name)
    try:
        result=Decimal(str(value))
    except (InvalidOperation,ValueError) as exc:
        raise ValueError("invalid "+name) from exc
    if not result.is_finite():
        raise ValueError("nonfinite "+name)
    return result


def _scenario_hypothesis(
    scorecard:Mapping[str,object],scenario:str,hypothesis:str,
) -> Mapping[str,object]:
    scenarios=scorecard.get("scenarios")
    if not isinstance(scenarios,Mapping) or scenario not in scenarios:
        raise ValueError("required prospective friction scenario missing")
    case=scenarios[scenario]
    if not isinstance(case,Mapping):
        raise ValueError("invalid prospective scenario")
    fixed=case.get("fixed_predeclared_hypotheses")
    if not isinstance(fixed,Mapping) or hypothesis not in fixed:
        raise ValueError("predeclared hypothesis result missing")
    result=fixed[hypothesis]
    if not isinstance(result,Mapping):
        raise ValueError("invalid hypothesis result")
    return result


def assess_forward_review_gate(
    scorecard:Mapping[str,object],
    *,
    policy:ForwardReviewPolicy=ForwardReviewPolicy(),
) -> dict[str,object]:
    """Return frozen criteria only; NEVER transform eligibility into trading."""
    if not isinstance(scorecard,Mapping):
        raise ValueError("prospective scorecard mapping required")
    if policy.policy_version!=POLICY_VERSION:
        raise ValueError("unexpected forward review policy")
    if scorecard.get("kind")!="OFFLINE_SIX_CRYPTO_PROSPECTIVE_SHADOW_SCORECARD":
        raise ValueError("wrong source report")
    if scorecard.get("broker_order_submission")!="DISABLED":
        raise ValueError("source report must be no-order")
    if scorecard.get("strategy_promoted") is not False:
        raise ValueError("source scorecard already claims a promoted strategy")
    if scorecard.get("future_edge_established") is not False:
        raise ValueError("source scorecard must not claim established edge")

    source_hours=scorecard.get("current_segment_prospective_source_hours")
    scored=scorecard.get("fully_observed_precommitted_decision_intervals")
    if type(source_hours) is not int or source_hours<0:
        raise ValueError("invalid prospective source-hour count")
    if type(scored) is not int or scored<0 or scored>max(0,source_hours-1):
        raise ValueError("invalid precommitted-outcome count")

    enough_source=source_hours>=policy.minimum_prospective_source_hours
    enough_scored=scored>=policy.minimum_fully_scored_outcomes
    complete=enough_source and enough_scored

    active_names=tuple(
        h.name for h in HYPOTHESES
        if h.kind in (HypothesisKind.EMA,HypothesisKind.MOMENTUM))
    comparator_names=tuple(
        h.name for h in HYPOTHESES
        if h.kind in (HypothesisKind.CASH,HypothesisKind.PASSIVE))
    if len(active_names)!=2 or len(comparator_names)!=2:
        raise ValueError("registered hypothesis roles changed; review gate must be versioned")
    passive=next(
        h.name for h in HYPOTHESES if h.kind==HypothesisKind.PASSIVE)

    assessments={}
    if complete:
        passive_base=_scenario_hypothesis(scorecard,BASE_SCENARIO,passive)
        passive_high=_scenario_hypothesis(scorecard,HIGH_SCENARIO,passive)
        passive_base_pnl=_money(
            passive_base["net_pnl_if_hypothetically_liquidated_usd"],
            "passive base P&L")
        passive_high_pnl=_money(
            passive_high["net_pnl_if_hypothetically_liquidated_usd"],
            "passive high P&L")

        for name in active_names:
            base=_scenario_hypothesis(scorecard,BASE_SCENARIO,name)
            high=_scenario_hypothesis(scorecard,HIGH_SCENARIO,name)
            base_pnl=_money(
                base["net_pnl_if_hypothetically_liquidated_usd"],
                name+" base P&L")
            high_pnl=_money(
                high["net_pnl_if_hypothetically_liquidated_usd"],
                name+" high P&L")
            base_dd=_money(base["sampled_event_max_drawdown_usd"],
                           name+" base drawdown")
            high_dd=_money(high["sampled_event_max_drawdown_usd"],
                           name+" high drawdown")
            fills=base.get("synthetic_fill_count")
            if type(fills) is not int or fills<0:
                raise ValueError("invalid base synthetic fill count")
            if (base.get("evaluated_precommitted_outcome_intervals")!=scored or
                    high.get("evaluated_precommitted_outcome_intervals")!=scored):
                raise ValueError("scenario outcome interval count differs from source scorecard")
            criteria={
                "minimum_169_source_hours":
                    source_hours>=policy.minimum_prospective_source_hours,
                "minimum_168_fully_observed_precommitted_outcomes":
                    scored>=policy.minimum_fully_scored_outcomes,
                "minimum_10_base_synthetic_fills":
                    fills>=policy.minimum_base_synthetic_fills,
                "base_exit_inclusive_pnl_positive":base_pnl>0,
                "high_exit_inclusive_pnl_positive":high_pnl>0,
                "base_outperforms_same_book_passive":
                    base_pnl>passive_base_pnl,
                "high_outperforms_same_book_passive":
                    high_pnl>passive_high_pnl,
                "base_sampled_drawdown_at_or_below_10_usd":
                    base_dd<=policy.maximum_sampled_drawdown_usd,
                "high_sampled_drawdown_at_or_below_10_usd":
                    high_dd<=policy.maximum_sampled_drawdown_usd,
                "base_no_persistent_peak_drawdown_halt":
                    base.get("persistent_peak_drawdown_entry_halt") is False,
                "high_no_persistent_peak_drawdown_halt":
                    high.get("persistent_peak_drawdown_entry_halt") is False,
            }
            failed=[key for key,value in criteria.items() if not value]
            assessments[name]={
                "role":"ACTIVE_RESEARCH_CANDIDATE",
                "criteria":criteria,
                "criteria_met":not failed,
                "failed_criteria":failed,
                "base_exit_inclusive_pnl_usd":str(base_pnl),
                "high_exit_inclusive_pnl_usd":str(high_pnl),
                "passive_base_comparator_pnl_usd":str(passive_base_pnl),
                "passive_high_comparator_pnl_usd":str(passive_high_pnl),
                "base_synthetic_fill_count":fills,
                "owner_paper_execution_design_review_eligible":not failed,
                "broker_order_submission":"DISABLED",
            }
    else:
        for name in active_names:
            assessments[name]={
                "role":"ACTIVE_RESEARCH_CANDIDATE",
                "criteria_met":False,
                "failed_criteria":[
                    "minimum_169_source_hours"
                    if not enough_source else None,
                    "minimum_168_fully_observed_precommitted_outcomes"
                    if not enough_scored else None,
                ],
                "owner_paper_execution_design_review_eligible":False,
                "broker_order_submission":"DISABLED",
            }
            assessments[name]["failed_criteria"]=[
                x for x in assessments[name]["failed_criteria"] if x]

    comparators={
        name:{
            "role":"COMPARATOR_NOT_PROMOTION_CANDIDATE",
            "owner_paper_execution_design_review_eligible":False,
            "broker_order_submission":"DISABLED",
        } for name in comparator_names
    }
    eligible=sorted(
        name for name,result in assessments.items()
        if result["owner_paper_execution_design_review_eligible"])
    return {
        "kind":"PREDECLARED_SIX_CRYPTO_FORWARD_REVIEW_GATE_NOT_TRADING_AUTHORIZATION",
        "policy_version":policy.policy_version,
        "policy_frozen_before_first_scored_six_crypto_outcome":True,
        "minimum_prospective_source_hours":
            policy.minimum_prospective_source_hours,
        "minimum_fully_scored_precommitted_outcomes":
            policy.minimum_fully_scored_outcomes,
        "minimum_base_synthetic_fills":
            policy.minimum_base_synthetic_fills,
        "maximum_sampled_drawdown_usd":
            str(policy.maximum_sampled_drawdown_usd),
        "current_prospective_source_hours":source_hours,
        "current_fully_scored_precommitted_outcomes":scored,
        "evidence_window_complete_for_gate":complete,
        "active_candidate_assessments":assessments,
        "comparators":comparators,
        "candidates_meeting_all_review_criteria":eligible,
        "candidate_order_has_no_rank_or_preference":True,
        "automatic_candidate_selection":"DISABLED",
        "paper_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
        "separate_owner_authorization_still_required_for_any_PAPER_execution":True,
        "passing_does_not_establish_future_profit":True,
    }

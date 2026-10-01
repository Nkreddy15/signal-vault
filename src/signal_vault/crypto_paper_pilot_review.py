"""Frozen review policy before any autonomous crypto PAPER pilot activation.

This policy does not submit, schedule, or authorize an order. It combines the
already-frozen six-crypto prospective strategy review with separately supplied
paper-engineering evidence. A pass only permits a distinct owner activation
review; actual PAPER activation remains a separate operation and LIVE trading
remains unavailable.
"""
from __future__ import annotations

from typing import Mapping

from .multi_asset_simulation import HYPOTHESES, HypothesisKind

KIND="CRYPTO_AUTONOMOUS_PAPER_PILOT_REVIEW_NOT_ACTIVATION"
POLICY_VERSION="crypto-autonomous-paper-pilot-review-v1-frozen-20261001"
ENGINEERING_KIND="CRYPTO_PAPER_PILOT_ENGINEERING_EVIDENCE"


def _bool(mapping:Mapping[str,object], name:str)->bool:
    value=mapping.get(name)
    if type(value) is not bool:
        raise ValueError(f"explicit boolean required for {name}")
    return value


def _count(mapping:Mapping[str,object], name:str)->int:
    value=mapping.get(name)
    if type(value) is not int or value<0:
        raise ValueError(f"nonnegative integer required for {name}")
    return value


def assess_crypto_paper_pilot_review(
    forward_review:Mapping[str,object],
    engineering:Mapping[str,object],
)->dict[str,object]:
    if (
        not isinstance(forward_review,Mapping)
        or forward_review.get("kind")
        !="PREDECLARED_SIX_CRYPTO_FORWARD_REVIEW_GATE_NOT_TRADING_AUTHORIZATION"
        or forward_review.get("paper_order_submission")!="DISABLED"
        or forward_review.get("live_trading")!="UNAVAILABLE"
        or forward_review.get(
            "separate_owner_authorization_still_required_for_any_PAPER_execution"
        ) is not True
    ):
        raise ValueError("invalid six-crypto forward review receipt")
    eligible=forward_review.get("candidates_meeting_all_review_criteria")
    active_candidates={
        h.name for h in HYPOTHESES
        if h.kind in (HypothesisKind.EMA,HypothesisKind.MOMENTUM)
    }
    if (
        not isinstance(eligible,list)
        or any(not isinstance(x,str) or not x for x in eligible)
        or len(set(eligible))!=len(eligible)
        or any(x not in active_candidates for x in eligible)
    ):
        raise ValueError("invalid eligible crypto candidate list")

    if (
        not isinstance(engineering,Mapping)
        or engineering.get("kind")!=ENGINEERING_KIND
        or engineering.get("environment")!="alpaca_paper"
        or engineering.get("live_host_requests")!=0
        or engineering.get("paper_order_submission")!="DISABLED"
        or engineering.get("live_order_submission")!="DISABLED"
    ):
        raise ValueError("invalid crypto paper engineering evidence")

    checks={
        "frozen_forward_review_window_complete":
            forward_review.get("evidence_window_complete_for_gate") is True,
        "at_least_one_candidate_meets_all_frozen_forward_criteria":
            bool(eligible),
        "supervised_paper_smoke_reconciled":
            _bool(engineering,"supervised_paper_smoke_reconciled"),
        "paper_host_only_verified":
            _bool(engineering,"paper_host_only_verified"),
        "fresh_provider_preflight_passed":
            _bool(engineering,"fresh_provider_preflight_passed"),
        "durable_commit_before_post_validated":
            _bool(engineering,"durable_commit_before_post_validated"),
        "duplicate_submission_prevention_validated":
            _bool(engineering,"duplicate_submission_prevention_validated"),
        "unknown_result_recovery_validated":
            _bool(engineering,"unknown_result_recovery_validated"),
        "provider_reconciliation_path_validated":
            _bool(engineering,"provider_reconciliation_path_validated"),
        "shared_cross_market_risk_governor_validated":
            _bool(engineering,"shared_cross_market_risk_governor_validated"),
        "zero_unresolved_paper_orders":
            _count(engineering,"unresolved_paper_orders")==0,
        "operator_not_halted":
            _bool(engineering,"operator_halted") is False,
    }
    failed=[name for name,value in checks.items() if not value]
    eligible_for_review=not failed
    return {
        "kind":KIND,
        "policy_version":POLICY_VERSION,
        "policy_frozen_before_autonomous_paper_activation":True,
        "candidate_order_has_no_rank_or_preference":True,
        "eligible_forward_candidates":list(eligible),
        "checks":checks,
        "failed_checks":failed,
        "eligible_for_separate_owner_paper_pilot_activation_review":
            eligible_for_review,
        "owner_autonomous_paper_authorization_recorded":False,
        "paper_pilot_activation_permitted":False,
        "automatic_paper_activation":"DISABLED",
        "paper_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
        "passing_is_not_expected_profit_or_trading_advice":True,
        "next_action":(
            "SEPARATE_OWNER_PAPER_PILOT_ACTIVATION_REVIEW_REQUIRED"
            if eligible_for_review else
            "COMPLETE_FAILED_TECHNICAL_OR_FORWARD_EVIDENCE_CHECKS"
        ),
    }

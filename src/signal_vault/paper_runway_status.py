"""Read-only paper-runway status derived from persisted all-market evidence.

This module answers an operational question: which research/evidence lane is
still blocking the next PAPER/DEMO design review? It never turns readiness into
authorization, never reads credentials, never performs provider requests, and
never submits an order.

Execution-system engineering and any prior supervised broker smoke are separate
from this cloud forward-evidence report. They are deliberately reported as
NOT_TRACKED rather than inferred from source files or historical notes.
"""
from __future__ import annotations

import json
from typing import Mapping

from .all_market_forward_status import all_market_forward_status


KIND="PAPER_RUNWAY_STATUS_NOT_ORDER_AUTHORIZATION"


def _nonnegative_int(raw:object, *, name:str)->int:
    if type(raw) is not int or raw<0:
        raise ValueError(f"invalid {name}")
    return raw


def _lane_action(status:Mapping[str,object], lane:str)->str:
    actions=status.get("lane_next_actions")
    if not isinstance(actions,Mapping):
        raise ValueError("all-market status lacks lane next actions")
    value=actions.get(lane)
    if not isinstance(value,str) or not value:
        raise ValueError("invalid lane next action")
    return value


def paper_runway_from_forward_status(status:Mapping[str,object])->dict[str,object]:
    """Summarize evidence runway without granting any execution authority."""
    if (
        not isinstance(status,Mapping)
        or status.get("kind")!="ALL_MARKET_FORWARD_READINESS_STATUS_NO_ORDERS"
        or status.get("broker_order_submission")!="DISABLED"
        or status.get("paper_order_submission")!="DISABLED"
        or status.get("demo_order_submission")!="DISABLED"
        or status.get("live_order_submission")!="DISABLED"
        or status.get("automatic_live_trading")!="DISABLED"
        or status.get("live_trading")!="UNAVAILABLE"
    ):
        raise ValueError("unsafe or malformed all-market forward status")

    crypto=status.get("btc_and_six_crypto")
    equity=status.get("us_equity")
    kalshi=status.get("kalshi")
    if not all(isinstance(x,Mapping) for x in (crypto,equity,kalshi)):
        raise ValueError("all-market status lacks required lane mappings")

    source_hours=_nonnegative_int(
        crypto.get("sidecar_current_segment_independent_prospective_hours",0),
        name="six-crypto prospective source hours",
    )
    scored=_nonnegative_int(
        crypto.get("sidecar_fully_observed_precommitted_decision_intervals",0),
        name="six-crypto scored outcomes",
    )
    source_remaining=_nonnegative_int(
        crypto.get("sidecar_review_gate_source_hours_remaining_to_169",max(0,169-source_hours)),
        name="six-crypto remaining source hours",
    )
    scored_remaining=_nonnegative_int(
        crypto.get("sidecar_review_gate_scored_outcomes_remaining_to_168",max(0,168-scored)),
        name="six-crypto remaining scored outcomes",
    )
    crypto_gate_complete=crypto.get("sidecar_review_gate_evidence_window_complete") is True
    eligible=crypto.get("sidecar_candidates_meeting_all_review_criteria",[])
    if not isinstance(eligible,list) or any(not isinstance(x,str) or not x for x in eligible):
        raise ValueError("invalid six-crypto candidate review list")

    equity_hours_remaining=_nonnegative_int(
        equity.get("raw_core_hour_receipts_remaining_to_60",60),
        name="equity remaining core-hour receipts",
    )
    equity_sessions_remaining=_nonnegative_int(
        equity.get("raw_session_plans_remaining_to_10",10),
        name="equity remaining session plans",
    )
    equity_source_ready=(
        equity.get("prospective_source_integrity_ready_for_shadow_scoring") is True
    )

    kalshi_snapshots_remaining=_nonnegative_int(
        kalshi.get("raw_decision_snapshots_remaining",40),
        name="Kalshi remaining decision snapshots",
    )
    kalshi_settlements_remaining=_nonnegative_int(
        kalshi.get("raw_settlement_receipts_remaining",20),
        name="Kalshi remaining settlements",
    )
    kalshi_source_ready=(
        kalshi.get("prospective_source_integrity_ready_for_shadow_scoring") is True
    )

    blockers=[]
    if not crypto_gate_complete:
        blockers.append("SIX_CRYPTO_FROZEN_FORWARD_REVIEW_WINDOW_INCOMPLETE")
    elif not eligible:
        blockers.append("SIX_CRYPTO_FORWARD_WINDOW_COMPLETE_NO_CANDIDATE_ELIGIBLE")
    if not equity_source_ready:
        blockers.append("US_EQUITY_PROSPECTIVE_SOURCE_NOT_READY_FOR_SHADOW_SCORING")
    if not kalshi_source_ready:
        blockers.append("KALSHI_PROSPECTIVE_SOURCE_NOT_READY_FOR_SHADOW_SCORING")

    return {
        "kind":KIND,
        "six_crypto":{
            "prospective_source_hours":source_hours,
            "fully_scored_precommitted_outcomes":scored,
            "source_hours_remaining_to_frozen_169_hour_gate":source_remaining,
            "scored_outcomes_remaining_to_frozen_168_outcome_gate":scored_remaining,
            "frozen_review_window_complete":crypto_gate_complete,
            "candidates_meeting_all_frozen_review_criteria":list(eligible),
            "next_action":_lane_action(status,"six_crypto"),
        },
        "us_equity":{
            "core_hour_receipts_remaining_to_60":equity_hours_remaining,
            "session_plans_remaining_to_10":equity_sessions_remaining,
            "prospective_source_integrity_ready_for_shadow_scoring":equity_source_ready,
            "next_action":_lane_action(status,"us_equity"),
        },
        "kalshi":{
            "plan_present":kalshi.get("plan_present") is True,
            "planned_market_count":kalshi.get("planned_market_count"),
            "decision_snapshots_remaining":kalshi_snapshots_remaining,
            "settlement_receipts_remaining":kalshi_settlements_remaining,
            "prospective_source_integrity_ready_for_shadow_scoring":kalshi_source_ready,
            "next_action":_lane_action(status,"kalshi"),
        },
        "current_forward_evidence_blockers":blockers,
        "all_market_forward_source_and_review_stages_complete":not blockers,
        "execution_engineering_and_prior_supervised_paper_smoke":
            "NOT_TRACKED_BY_THIS_CLOUD_FORWARD_STATUS",
        "provider_paper_or_demo_execution_validation":
            "NOT_TRACKED_BY_THIS_CLOUD_FORWARD_STATUS",
        "owner_authorization_required_for_any_new_paper_or_demo_submission":True,
        "automatic_paper_or_demo_submission":"DISABLED",
        "broker_order_submission":"DISABLED",
        "paper_order_submission":"DISABLED",
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
        "network_requests":"NONE",
        "credential_access":"NONE",
        "readiness_is_not_expected_profit_or_trading_advice":True,
    }


def current_paper_runway()->dict[str,object]:
    return paper_runway_from_forward_status(all_market_forward_status())


def main()->int:
    try:
        result=current_paper_runway()
        print(json.dumps(result,sort_keys=True,indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "kind":KIND,
            "status":"FAIL_CLOSED",
            "failure_class":type(exc).__name__,
            "network_requests":"NONE",
            "credential_access":"NONE",
            "broker_order_submission":"DISABLED",
            "paper_order_submission":"DISABLED",
            "demo_order_submission":"DISABLED",
            "live_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        },sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())

"""Provider-neutral PAPER/DEMO intent preview with shared risk assessment.

This module compiles a precommitted strategy decision into a validated
MultiMarketOrderDraft and paper/demo route preview. It has no network client,
reads no credentials, writes no execution journal, and can never submit an
order. Its output is engineering evidence only.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Mapping

from .cross_market_risk import (
    CrossMarketRiskLimits,
    LANES,
    assess_new_risk,
)
from .multimarket_execution_journal import MultiMarketOrderDraft
from .multimarket_paper_router import route_paper_execution


KIND="MULTIMARKET_PAPER_INTENT_PREVIEW_NO_ORDERS"
DECISION_KIND="PRECOMMITTED_MULTIMARKET_PAPER_DECISION_INTENT"


def _decimal(raw:object, *, name:str, allow_zero:bool=False)->Decimal:
    try:
        value=Decimal(str(raw))
    except (InvalidOperation,ValueError,TypeError) as exc:
        raise ValueError(f"invalid {name}") from exc
    if not value.is_finite() or value < 0 or (not allow_zero and value==0):
        raise ValueError(f"invalid {name}")
    return value


def _account_state(raw:Mapping[str,object])->dict[str,object]:
    required={
        "exposure_by_lane","open_positions","marked_equity_usd",
        "daily_anchor_equity_usd","peak_equity_usd","operator_halted",
    }
    if set(raw)!=required:
        raise ValueError("exact account state fields required")
    exposure_raw=raw["exposure_by_lane"]
    if not isinstance(exposure_raw,Mapping) or set(exposure_raw)!=set(LANES):
        raise ValueError("exact cross-market exposure lanes required")
    exposure={
        lane:_decimal(exposure_raw[lane],name=f"{lane} exposure",allow_zero=True)
        for lane in LANES
    }
    open_positions=raw["open_positions"]
    operator_halted=raw["operator_halted"]
    if type(open_positions) is not int or open_positions<0:
        raise ValueError("invalid open position count")
    if type(operator_halted) is not bool:
        raise ValueError("explicit operator halt boolean required")
    return {
        "exposure_by_lane":exposure,
        "open_positions":open_positions,
        "marked_equity_usd":_decimal(
            raw["marked_equity_usd"],name="marked equity",allow_zero=True
        ),
        "daily_anchor_equity_usd":_decimal(
            raw["daily_anchor_equity_usd"],name="daily anchor",allow_zero=True
        ),
        "peak_equity_usd":_decimal(
            raw["peak_equity_usd"],name="peak equity",allow_zero=True
        ),
        "operator_halted":operator_halted,
    }


def preview_paper_intent(
    decision:Mapping[str,object],
    *,
    account_state:Mapping[str,object],
    limits:CrossMarketRiskLimits=CrossMarketRiskLimits(),
)->dict[str,object]:
    if not isinstance(decision,Mapping) or decision.get("kind")!=DECISION_KIND:
        raise ValueError("invalid precommitted paper decision intent")
    required={
        "kind","decision_id","market_lane","instrument","max_loss_usd",
        "provider_payload","strategy_evidence_sha256",
        "forward_gate_passed","separate_owner_activation_required",
    }
    if set(decision)!=required:
        raise ValueError("exact paper decision intent fields required")
    lane=decision["market_lane"]
    if lane not in LANES:
        raise ValueError("unsupported market lane")
    decision_id=decision["decision_id"]
    instrument=decision["instrument"]
    evidence_sha=decision["strategy_evidence_sha256"]
    if (
        not isinstance(decision_id,str) or not 1<=len(decision_id)<=48
        or not all(ch.isalnum() or ch in "_-" for ch in decision_id)
    ):
        raise ValueError("invalid decision id")
    if (
        not isinstance(instrument,str) or not instrument.strip()
        or len(instrument)>160
    ):
        raise ValueError("invalid instrument")
    if (
        not isinstance(evidence_sha,str) or len(evidence_sha)!=64
        or any(ch not in "0123456789abcdef" for ch in evidence_sha)
    ):
        raise ValueError("lowercase SHA-256 strategy evidence required")
    if type(decision["forward_gate_passed"]) is not bool:
        raise ValueError("explicit forward gate boolean required")
    if decision["separate_owner_activation_required"] is not True:
        raise ValueError("owner activation requirement must remain explicit")
    payload=decision["provider_payload"]
    if not isinstance(payload,Mapping) or not payload:
        raise ValueError("provider payload mapping required")
    if any(not isinstance(k,str) or not isinstance(v,str) for k,v in payload.items()):
        raise ValueError("provider payload must be string-only")

    max_loss=_decimal(decision["max_loss_usd"],name="max loss")
    account=_account_state(account_state)
    risk=assess_new_risk(
        lane=lane,
        proposed_max_loss_usd=max_loss,
        exposure_by_lane=account["exposure_by_lane"],
        open_positions=account["open_positions"],
        marked_equity_usd=account["marked_equity_usd"],
        daily_anchor_equity_usd=account["daily_anchor_equity_usd"],
        peak_equity_usd=account["peak_equity_usd"],
        operator_halted=account["operator_halted"],
        limits=limits,
    )
    draft=MultiMarketOrderDraft(
        client_order_id=decision_id,
        market_lane=lane,
        instrument=instrument,
        max_loss_usd=max_loss,
        payload=dict(payload),
    )

    route=None
    route_status="NOT_ROUTED_RISK_REJECTED"
    if risk["risk_admissible"] is True:
        route=route_paper_execution(
            draft,
            risk_assessment=risk,
            acknowledgement="",
        )
        route_status="VALIDATED_PREVIEW_NO_SUBMISSION"

    return {
        "kind":KIND,
        "decision_id":decision_id,
        "market_lane":lane,
        "instrument":instrument,
        "strategy_evidence_sha256":evidence_sha,
        "forward_gate_passed":decision["forward_gate_passed"],
        "risk_assessment":risk,
        "route_status":route_status,
        "route":(route.as_dict() if route is not None else None),
        "durable_execution_journal_write":"NONE",
        "network_requests":"NONE",
        "credentials_accessed":"NONE",
        "provider_post_attempted":False,
        "owner_activation_required":True,
        "automatic_paper_or_demo_submission":"DISABLED",
        "paper_order_submission":"DISABLED",
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
        "preview_is_not_trading_authorization":True,
    }

"""Persist a supervised historical-bootstrap crypto PAPER draft.

This bridge accepts only the Phase 134 supervised PAPER preview. It never
pretends the independent 168-hour forward gate passed. It persists the same
provider-neutral MultiMarketOrderDraft used by the existing PAPER executor
stack, with no network access and no order submission.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Mapping

from .crypto_paper_executor_draft import KIND as PREPARED_KIND
from .historical_bootstrap_supervised_paper import (
    KIND as REVIEW_KIND,
)
from .multimarket_execution_journal import (
    MultiMarketExecutionJournal,
    MultiMarketOrderDraft,
)
from .multimarket_paper_router import CRYPTO_PAPER_ACK


SOURCE_KIND="CRYPTO_HISTORICAL_BOOTSTRAP_SUPERVISED_PAPER_PREVIEW_NO_ORDERS"


def _positive(raw:object,name:str)->Decimal:
    try:
        value=Decimal(str(raw))
    except (InvalidOperation,ValueError,TypeError) as exc:
        raise ValueError(f"invalid {name}") from exc
    if not value.is_finite() or value<=0 or value>Decimal("5"):
        raise ValueError(f"invalid {name}")
    return value


def persist_bootstrap_crypto_paper_draft(
    bootstrap_preview:Mapping[str,object],
    *,
    journal:MultiMarketExecutionJournal,
    at:datetime,
)->dict[str,object]:
    if (
        not isinstance(bootstrap_preview,Mapping)
        or bootstrap_preview.get("kind")!=SOURCE_KIND
        or bootstrap_preview.get("status")!="READY_FOR_SUPERVISED_PAPER_DRAFT_REVIEW"
        or bootstrap_preview.get("automatic_paper_activation")!="DISABLED"
        or bootstrap_preview.get("provider_post_attempted") is not False
        or bootstrap_preview.get("paper_order_submission")!="DISABLED"
        or bootstrap_preview.get("live_trading")!="UNAVAILABLE"
        or bootstrap_preview.get("independent_prospective_gate_passed") is not False
        or bootstrap_preview.get("paper_period_is_forward_validation") is not True
        or bootstrap_preview.get("live_promotion_permitted") is not False
    ):
        raise ValueError("eligible historical-bootstrap PAPER preview required")

    review=bootstrap_preview.get("historical_review")
    preview=bootstrap_preview.get("paper_preview")
    if (
        not isinstance(review,Mapping)
        or review.get("kind")!=REVIEW_KIND
        or review.get("eligible_for_supervised_paper_bootstrap") is not True
        or review.get("independent_prospective_gate_passed") is not False
        or review.get("automatic_paper_activation")!="DISABLED"
        or review.get("live_trading")!="UNAVAILABLE"
        or not isinstance(preview,Mapping)
        or preview.get("market_lane")!="crypto"
        or preview.get("instrument")!="BTC/USD"
        or preview.get("forward_gate_passed") is not False
        or preview.get("provider_post_attempted") is not False
        or preview.get("paper_order_submission")!="DISABLED"
        or preview.get("live_trading")!="UNAVAILABLE"
    ):
        raise ValueError("historical review/current PAPER preview mismatch")

    route=preview.get("route")
    risk=preview.get("risk_assessment")
    if (
        not isinstance(route,Mapping)
        or route.get("provider")!="alpaca"
        or route.get("environment")!="paper"
        or route.get("market_lane")!="crypto"
        or route.get("required_acknowledgement")!=CRYPTO_PAPER_ACK
        or route.get("live_trading_available") is not False
        or not isinstance(route.get("payload"),Mapping)
        or not isinstance(risk,Mapping)
        or risk.get("kind")!="CROSS_MARKET_RISK_ASSESSMENT_NOT_ORDER_AUTHORIZATION"
        or risk.get("lane")!="crypto"
        or risk.get("risk_admissible") is not True
        or risk.get("assessment_is_not_trading_authorization") is not True
        or risk.get("automatic_order_submission")!="DISABLED"
    ):
        raise ValueError("matching admissible PAPER route/risk receipt required")

    decision_id=preview.get("decision_id")
    payload=route["payload"]
    if (
        not isinstance(decision_id,str) or not decision_id
        or payload.get("client_order_id")!=decision_id
        or payload.get("symbol")!="BTC/USD"
        or any(not isinstance(k,str) or not isinstance(v,str) for k,v in payload.items())
    ):
        raise ValueError("bootstrap PAPER payload identity mismatch")

    max_loss=_positive(risk.get("proposed_max_loss_usd"),"proposed PAPER max loss")
    if _positive(payload.get("notional"),"PAPER notional")!=max_loss:
        raise ValueError("PAPER notional and shared-risk max loss must match")
    if journal.has_unresolved():
        raise PermissionError("unresolved cross-market order blocks new PAPER draft")

    draft=MultiMarketOrderDraft(
        client_order_id=decision_id,
        market_lane="crypto",
        instrument="BTC/USD",
        max_loss_usd=max_loss,
        payload=dict(payload),
    )
    journal.record_approved_draft(draft,at=at)
    return {
        "kind":PREPARED_KIND,
        "status":"DURABLE_CRYPTO_PAPER_DRAFT_APPROVED_NOT_SUBMITTED",
        "source_mode":"HISTORICAL_BOOTSTRAP_SUPERVISED_PAPER",
        "independent_prospective_gate_passed":False,
        "paper_period_is_forward_validation":True,
        "decision_id":draft.client_order_id,
        "market_lane":draft.market_lane,
        "instrument":draft.instrument,
        "max_loss_usd":str(draft.max_loss_usd),
        "payload_sha256":draft.payload_sha256,
        "required_acknowledgement":CRYPTO_PAPER_ACK,
        "execution_journal_write_performed":True,
        "provider_post_attempted":False,
        "paper_executor_invoked":False,
        "paper_order_submission":"DISABLED",
        "live_order_submission":"UNAVAILABLE",
        "live_trading":"UNAVAILABLE",
        "next_action":"FRESH_ALPACA_PAPER_PREFLIGHT_REQUIRED_BEFORE_ANY_SUPERVISED_POST",
    }

"""Persist an approved crypto PAPER execution draft after the full dry-run gate.

This is the final durable handoff before a separate one-shot Alpaca PAPER
executor invocation. It writes only the local cross-market execution journal.
It reads no credentials, performs no provider request, and cannot submit an
order.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Mapping

from .crypto_paper_pilot_dry_run import KIND as DRY_RUN_KIND
from .crypto_paper_activation_handoff import KIND as HANDOFF_KIND
from .paper_intent_preview import KIND as PREVIEW_KIND
from .multimarket_execution_journal import (
    MultiMarketExecutionJournal,
    MultiMarketOrderDraft,
)
from .multimarket_paper_router import CRYPTO_PAPER_ACK


KIND="CRYPTO_PAPER_EXECUTOR_DRAFT_PERSISTED_NOT_SUBMITTED"


def _positive_decimal(raw:object, *, name:str)->Decimal:
    try:
        value=Decimal(str(raw))
    except (InvalidOperation,ValueError,TypeError) as exc:
        raise ValueError(f"invalid {name}") from exc
    if not value.is_finite() or value<=0:
        raise ValueError(f"invalid {name}")
    return value


def persist_crypto_paper_executor_draft(
    dry_run:Mapping[str,object],
    *,
    journal:MultiMarketExecutionJournal,
    at:datetime,
)->dict[str,object]:
    if (
        not isinstance(dry_run,Mapping)
        or dry_run.get("kind")!=DRY_RUN_KIND
        or dry_run.get("status")!="READY_FOR_SEPARATE_PAPER_EXECUTOR_INVOCATION_REVIEW"
        or dry_run.get("eligible_for_separate_paper_executor_invocation_review") is not True
        or dry_run.get("provider_post_attempted") is not False
        or dry_run.get("paper_executor_invoked") is not False
        or dry_run.get("paper_order_submission")!="DISABLED"
        or dry_run.get("live_trading")!="UNAVAILABLE"
    ):
        raise ValueError("eligible no-execution crypto PAPER dry run required")

    preview=dry_run.get("paper_preview")
    handoff=dry_run.get("activation_handoff")
    if (
        not isinstance(preview,Mapping)
        or preview.get("kind")!=PREVIEW_KIND
        or preview.get("market_lane")!="crypto"
        or preview.get("route_status")!="VALIDATED_PREVIEW_NO_SUBMISSION"
        or preview.get("provider_post_attempted") is not False
        or preview.get("paper_order_submission")!="DISABLED"
        or preview.get("live_trading")!="UNAVAILABLE"
    ):
        raise ValueError("validated crypto PAPER preview required")
    if (
        not isinstance(handoff,Mapping)
        or handoff.get("kind")!=HANDOFF_KIND
        or handoff.get("eligible_for_separate_paper_executor_invocation_review") is not True
        or handoff.get("executor_invocation_performed") is not False
        or handoff.get("execution_journal_write_performed") is not False
        or handoff.get("provider_post_attempted") is not False
        or handoff.get("paper_order_submission")!="DISABLED"
        or handoff.get("live_trading")!="UNAVAILABLE"
    ):
        raise ValueError("eligible crypto PAPER activation handoff required")

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
        or risk.get("risk_admissible") is not True
        or risk.get("assessment_is_not_trading_authorization") is not True
    ):
        raise ValueError("paper-only Alpaca route and admissible risk receipt required")

    decision_id=preview.get("decision_id")
    instrument=preview.get("instrument")
    payload=route["payload"]
    if (
        not isinstance(decision_id,str) or not decision_id
        or not isinstance(instrument,str) or not instrument
        or any(not isinstance(k,str) or not isinstance(v,str) for k,v in payload.items())
    ):
        raise ValueError("invalid crypto PAPER draft identity or payload")
    if payload.get("client_order_id")!=decision_id:
        raise ValueError("route payload client id mismatch")
    if payload.get("symbol")!=instrument:
        raise ValueError("route payload instrument mismatch")

    max_loss=_positive_decimal(
        risk.get("proposed_max_loss_usd"),
        name="previewed max loss",
    )
    handoff_loss=_positive_decimal(
        handoff.get("previewed_max_loss_usd"),
        name="handoff previewed max loss",
    )
    if max_loss!=handoff_loss:
        raise ValueError("risk and handoff max-loss mismatch")

    draft=MultiMarketOrderDraft(
        client_order_id=decision_id,
        market_lane="crypto",
        instrument=instrument,
        max_loss_usd=max_loss,
        payload=dict(payload),
    )
    if journal.has_unresolved():
        raise PermissionError("unresolved cross-market order blocks new PAPER draft")

    journal.record_approved_draft(draft,at=at)
    return {
        "kind":KIND,
        "status":"DURABLE_CRYPTO_PAPER_DRAFT_APPROVED_NOT_SUBMITTED",
        "decision_id":draft.client_order_id,
        "market_lane":draft.market_lane,
        "instrument":draft.instrument,
        "max_loss_usd":str(draft.max_loss_usd),
        "payload_sha256":draft.payload_sha256,
        "required_acknowledgement":CRYPTO_PAPER_ACK,
        "durable_execution_journal_write":"DRAFT_APPROVED_ONLY",
        "execution_journal_write_performed":True,
        "provider_post_attempted":False,
        "paper_executor_invoked":False,
        "network_requests":"NONE",
        "credentials_accessed":"NONE",
        "automatic_paper_submission":"DISABLED",
        "paper_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
        "next_action":
            "SEPARATE_ONE_SHOT_ALPACA_PAPER_EXECUTOR_REQUIRES_EXACT_ACK_AND_PAPER_CREDENTIALS",
        "receipt_is_not_order_authorization":True,
    }

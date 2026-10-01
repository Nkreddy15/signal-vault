"""Explicit one-shot crypto PAPER executor bridge.

This module can submit exactly one Alpaca PAPER order only when:
- the Phase 115 dry run is fully eligible,
- the Phase 118 durable draft receipt matches the journal,
- the shared risk receipt is still admissible,
- the exact crypto PAPER acknowledgement is supplied,
- separate PAPER credentials are supplied explicitly.

No LIVE host or LIVE execution path exists here.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Mapping

from .crypto_paper_executor_draft import KIND as PREPARED_KIND
from .crypto_paper_pilot_dry_run import KIND as DRY_RUN_KIND
from .crypto_paper_provider_preflight import KIND as PREFLIGHT_KIND
from .multimarket_alpaca_paper_executor import (
    MultiMarketAlpacaPaperOnceExecutor,
    _post_alpaca_paper,
)
from .multimarket_execution_journal import MultiMarketExecutionJournal
from .multimarket_paper_router import CRYPTO_PAPER_ACK


KIND="CRYPTO_ONE_SHOT_ALPACA_PAPER_EXECUTION"
MAX_PROVIDER_PREFLIGHT_AGE=timedelta(minutes=5)


def execute_prepared_crypto_paper_once(
    prepared:Mapping[str,object],
    dry_run:Mapping[str,object],
    *,
    journal:MultiMarketExecutionJournal,
    paper_key:str,
    paper_secret:str,
    acknowledgement:str,
    at:datetime,
    transport:Callable[
        [Mapping[str,str],str,str],Mapping[str,object]
    ]=_post_alpaca_paper,
)->dict[str,object]:
    if (
        not isinstance(prepared,Mapping)
        or prepared.get("kind")!=PREPARED_KIND
        or prepared.get("status")!="DURABLE_CRYPTO_PAPER_DRAFT_APPROVED_NOT_SUBMITTED"
        or prepared.get("market_lane")!="crypto"
        or prepared.get("provider_post_attempted") is not False
        or prepared.get("paper_executor_invoked") is not False
        or prepared.get("paper_order_submission")!="DISABLED"
        or prepared.get("live_trading")!="UNAVAILABLE"
    ):
        raise ValueError("valid persisted crypto PAPER draft receipt required")
    if (
        not isinstance(dry_run,Mapping)
        or dry_run.get("kind")!=DRY_RUN_KIND
        or dry_run.get("status")!="READY_FOR_SEPARATE_PAPER_EXECUTOR_INVOCATION_REVIEW"
        or dry_run.get("eligible_for_separate_paper_executor_invocation_review") is not True
        or dry_run.get("provider_post_attempted") is not False
        or dry_run.get("paper_executor_invoked") is not False
        or dry_run.get("live_trading")!="UNAVAILABLE"
    ):
        raise ValueError("eligible crypto PAPER dry run required")
    if acknowledgement!=CRYPTO_PAPER_ACK:
        raise PermissionError("exact crypto PAPER acknowledgement required")
    if not isinstance(paper_key,str) or not paper_key.strip():
        raise ValueError("separate Alpaca PAPER key required")
    if not isinstance(paper_secret,str) or not paper_secret.strip():
        raise ValueError("separate Alpaca PAPER secret required")

    preview=dry_run.get("paper_preview")
    if not isinstance(preview,Mapping):
        raise ValueError("paper preview required")
    risk=preview.get("risk_assessment")
    route=preview.get("route")
    if (
        not isinstance(risk,Mapping)
        or risk.get("risk_admissible") is not True
        or risk.get("assessment_is_not_trading_authorization") is not True
        or not isinstance(route,Mapping)
        or route.get("provider")!="alpaca"
        or route.get("environment")!="paper"
        or route.get("market_lane")!="crypto"
        or route.get("required_acknowledgement")!=CRYPTO_PAPER_ACK
        or route.get("live_trading_available") is not False
    ):
        raise ValueError("validated crypto Alpaca PAPER preview required")

    decision_id=prepared.get("decision_id")
    if (
        not isinstance(decision_id,str) or not decision_id
        or preview.get("decision_id")!=decision_id
    ):
        raise ValueError("prepared receipt and preview decision mismatch")

    draft=journal.get_approved_draft(decision_id)
    if (
        draft.market_lane!="crypto"
        or draft.instrument!=prepared.get("instrument")
        or draft.payload_sha256!=prepared.get("payload_sha256")
        or str(draft.max_loss_usd)!=str(prepared.get("max_loss_usd"))
    ):
        raise ValueError("durable approved draft does not match prepared receipt")
    if str(risk.get("proposed_max_loss_usd"))!=str(draft.max_loss_usd):
        raise ValueError("durable draft and risk receipt max-loss mismatch")

    preflight,captured_at,_=journal.get_provider_preflight_record(decision_id)
    execution_at=at.astimezone(timezone.utc)
    age=execution_at-captured_at
    if age<timedelta(0) or age>MAX_PROVIDER_PREFLIGHT_AGE:
        raise PermissionError("fresh provider PAPER preflight required at execution boundary")
    venue=preflight.get("venue_rules")
    if (
        preflight.get("kind")!=PREFLIGHT_KIND
        or preflight.get("decision_id")!=decision_id
        or preflight.get("market_lane")!="crypto"
        or preflight.get("instrument")!="BTC/USD"
        or preflight.get("environment")!="alpaca_paper"
        or preflight.get("account_active") is not True
        or preflight.get("trading_blocked") is not False
        or preflight.get("provider_positions_count")!=0
        or preflight.get("provider_open_orders_count")!=0
        or preflight.get("draft_payload_sha256")!=draft.payload_sha256
        or preflight.get("credential_values_persisted") is not False
        or preflight.get("provider_account_id_persisted") is not False
        or preflight.get("provider_post_attempted") is not False
        or preflight.get("paper_order_submission")!="DISABLED"
        or preflight.get("live_trading")!="UNAVAILABLE"
        or not isinstance(venue,Mapping)
        or venue.get("symbol")!="BTC/USD"
    ):
        raise PermissionError("valid persisted provider PAPER preflight required")
    if Decimal(str(preflight.get("non_marginable_buying_power_usd","0")))<draft.max_loss_usd:
        raise PermissionError("provider PAPER buying power below draft max loss")

    executor=MultiMarketAlpacaPaperOnceExecutor(
        paper_key=paper_key,
        paper_secret=paper_secret,
        journal=journal,
        transport=transport,
    )
    outcome=executor.submit_once(
        draft,
        risk_assessment=risk,
        acknowledgement=acknowledgement,
        at=at,
    )
    return {
        "kind":KIND,
        "status":"ALPACA_PAPER_POST_ATTEMPT_RECORDED",
        "decision_id":draft.client_order_id,
        "market_lane":draft.market_lane,
        "instrument":draft.instrument,
        "stage":outcome.stage.value,
        "provider_status":outcome.state.provider_status,
        "broker_order_id_recorded":outcome.state.broker_order_id is not None,
        "cumulative_filled_qty":str(outcome.state.cumulative_filled_qty),
        "paper_post_attempted":outcome.paper_post_attempted,
        "paper_executor_invoked":True,
        "execution_journal_write_performed":True,
        "environment":"alpaca_paper",
        "live_host_available":False,
        "live_order_submission":"UNAVAILABLE",
        "live_trading":"UNAVAILABLE",
        "blind_retry_forbidden":True,
        "next_action":(
            "RECONCILE_PROVIDER_STATE_BEFORE_ANY_NEW_EXECUTION"
            if outcome.state.blocks_new_execution else
            "AUDIT_TERMINAL_PAPER_ORDER_BEFORE_ANY_NEW_EXECUTION"
        ),
    }

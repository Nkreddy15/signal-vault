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
from .crypto_paper_provider_preflight import KIND as PREFLIGHT_KIND
from .crypto_paper_pilot_dry_run import KIND as DRY_RUN_KIND
from .multimarket_alpaca_paper_executor import (
    MultiMarketAlpacaPaperOnceExecutor,
    _post_alpaca_paper,
)
from .multimarket_execution_journal import MultiMarketExecutionJournal
from .multimarket_paper_router import CRYPTO_PAPER_ACK


KIND="CRYPTO_ONE_SHOT_ALPACA_PAPER_EXECUTION"


def execute_prepared_crypto_paper_once(
    prepared:Mapping[str,object],
    dry_run:Mapping[str,object],
    *,
    journal:MultiMarketExecutionJournal,
    paper_key:str,
    paper_secret:str,
    acknowledgement:str,
    preflight:Mapping[str,object],
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
    if not isinstance(preflight,Mapping):
        raise ValueError("fresh persisted provider preflight receipt required")
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

    record=journal.get_provider_preflight_record(decision_id)
    stored_preflight=record["receipt"]
    venue_rules=preflight.get("venue_rules")
    if (
        preflight.get("kind")!=PREFLIGHT_KIND
        or preflight.get("status")!="FRESH_PROVIDER_PREFLIGHT_PERSISTED"
        or preflight.get("decision_id")!=decision_id
        or preflight.get("market_lane")!="crypto"
        or preflight.get("instrument")!="BTC/USD"
        or preflight.get("environment")!="alpaca_paper"
        or preflight.get("account_active") is not True
        or preflight.get("trading_blocked") is not False
        or preflight.get("provider_positions_count")!=0
        or preflight.get("provider_open_orders_count")!=0
        or preflight.get("credential_values_persisted") is not False
        or preflight.get("provider_account_id_persisted") is not False
        or preflight.get("provider_post_attempted") is not False
        or preflight.get("paper_order_submission")!="DISABLED"
        or preflight.get("live_trading")!="UNAVAILABLE"
        or preflight.get("draft_payload_sha256")!=prepared.get("payload_sha256")
        or preflight.get("receipt_sha256")!=record["receipt_sha256"]
        or not isinstance(venue_rules,Mapping)
        or venue_rules.get("symbol")!="BTC/USD"
    ):
        raise ValueError("matching fresh provider preflight receipt required")
    try:
        buying_power=Decimal(str(preflight.get("non_marginable_buying_power_usd")))
        min_order=Decimal(str(venue_rules.get("min_order_size")))
        min_increment=Decimal(str(venue_rules.get("min_trade_increment")))
        price_increment=Decimal(str(venue_rules.get("price_increment")))
    except Exception as exc:
        raise ValueError("invalid provider preflight numeric fields") from exc
    if (
        not buying_power.is_finite() or buying_power<0
        or any(not x.is_finite() or x<=0
               for x in (min_order,min_increment,price_increment))
    ):
        raise ValueError("invalid provider preflight numeric fields")
    comparable=dict(preflight)
    comparable.pop("status",None)
    comparable.pop("receipt_sha256",None)
    comparable.pop("next_action",None)
    if comparable!=stored_preflight:
        raise ValueError("provided and durable preflight receipts differ")
    try:
        captured=datetime.fromisoformat(str(record["captured_utc"]))
    except ValueError as exc:
        raise ValueError("invalid durable preflight capture time") from exc
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("durable preflight capture time must be timezone-aware")
    current=at.astimezone(timezone.utc)
    captured=captured.astimezone(timezone.utc)
    age=current-captured
    if age<timedelta(0) or age>timedelta(minutes=5):
        raise PermissionError("provider preflight is stale or from the future")

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

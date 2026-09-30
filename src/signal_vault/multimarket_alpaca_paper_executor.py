"""Single-attempt Alpaca PAPER executor for crypto and US equities.

This executor consumes a durable MultiMarketOrderDraft plus the shared risk
assessment and Phase 34 paper route. It hardcodes Alpaca PAPER only, persists
SUBMISSION_PENDING before any POST, converts uncertain transport outcomes to
UNKNOWN_RESULT, and never blind-retries.

REAL PAPER WARNING: with real paper credentials and the exact market-specific
acknowledgement, submit_once can place an Alpaca PAPER order. No live host exists
in this module.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Callable, Mapping
from urllib.request import Request, build_opener

from .alpaca_paper import _NoRedirects
from .multimarket_execution_journal import (
    MultiMarketExecutionJournal,
    MultiMarketOrderDraft,
)
from .multimarket_paper_router import (
    ALPACA_PAPER_ROOT,
    paper_submission_authorized,
    route_paper_execution,
)
from .paper_order_state import BrokerObservation, PaperOrderState, Stage

_ORDER_PATH="/v2/orders"


def _post_alpaca_paper(
    payload:Mapping[str,str],
    key:str,
    secret:str,
)->Mapping[str,object]:
    if not key.strip() or not secret.strip():
        raise ValueError("separate Alpaca PAPER credentials required")
    req=Request(
        ALPACA_PAPER_ROOT+_ORDER_PATH,
        method="POST",
        data=json.dumps(dict(payload),separators=(",",":")).encode(),
        headers={
            "APCA-API-KEY-ID":key,
            "APCA-API-SECRET-KEY":secret,
            "Accept":"application/json",
            "Content-Type":"application/json",
            "User-Agent":"SignalVault/0.4",
        },
    )
    with build_opener(_NoRedirects).open(req,timeout=12) as response:
        raw=response.read(1_000_001)
    if len(raw)>1_000_000:
        raise ValueError("Alpaca paper response too large")
    decoded=json.loads(raw)
    if not isinstance(decoded,dict):
        raise ValueError("malformed Alpaca paper response")
    return decoded


def parse_alpaca_paper_observation(
    data:Mapping[str,object],
    *,
    expected_client_id:str,
)->BrokerObservation:
    if not isinstance(data,Mapping):
        raise ValueError("invalid Alpaca paper response")
    if data.get("client_order_id")!=expected_client_id:
        raise ValueError("Alpaca client order id mismatch")
    broker_id=data.get("id")
    status=data.get("status")
    if not isinstance(broker_id,str) or not broker_id:
        raise ValueError("missing Alpaca paper order id")
    if not isinstance(status,str) or not status:
        raise ValueError("missing Alpaca paper order status")
    try:
        filled_qty=Decimal(str(data.get("filled_qty","0")))
        raw_avg=data.get("filled_avg_price")
        avg=Decimal(str(raw_avg)) if raw_avg is not None else None
    except Exception as exc:
        raise ValueError("invalid Alpaca paper fill fields") from exc
    return BrokerObservation(
        expected_client_id,
        broker_id,
        status,
        filled_qty,
        avg,
    )


@dataclass(frozen=True)
class MultiMarketPaperSubmissionOutcome:
    market_lane:str
    stage:Stage
    explanation:str
    state:PaperOrderState
    paper_post_attempted:bool


class MultiMarketAlpacaPaperOnceExecutor:
    """Exactly one Alpaca PAPER POST attempt after durable/risk/ack gates."""

    def __init__(
        self,
        *,
        paper_key:str,
        paper_secret:str,
        journal:MultiMarketExecutionJournal,
        transport:Callable[
            [Mapping[str,str],str,str],Mapping[str,object]
        ]=_post_alpaca_paper,
    )->None:
        if not paper_key.strip() or not paper_secret.strip():
            raise ValueError("Alpaca PAPER credentials required")
        self._key=paper_key
        self._secret=paper_secret
        self._journal=journal
        self._transport=transport

    def submit_once(
        self,
        draft:MultiMarketOrderDraft,
        *,
        risk_assessment:Mapping[str,object],
        acknowledgement:str,
        at:datetime,
    )->MultiMarketPaperSubmissionOutcome:
        route=route_paper_execution(
            draft,
            risk_assessment=risk_assessment,
            acknowledgement=acknowledgement,
        )
        if route.provider!="alpaca" or route.environment!="paper":
            raise PermissionError("this executor accepts Alpaca PAPER routes only")
        if route.endpoint!=ALPACA_PAPER_ROOT+_ORDER_PATH:
            raise PermissionError("unexpected Alpaca paper endpoint")
        if not paper_submission_authorized(route,acknowledgement):
            raise PermissionError("exact market-specific PAPER acknowledgement required")

        self._journal.begin_submission(draft,at=at)
        try:
            response=self._transport(route.payload,self._key,self._secret)
            observation=parse_alpaca_paper_observation(
                response,
                expected_client_id=draft.client_order_id,
            )
            state=self._journal.observe_provider(observation,at=at)
            return MultiMarketPaperSubmissionOutcome(
                draft.market_lane,
                state.stage,
                "Alpaca PAPER response recorded; accepted is not assumed filled",
                state,
                True,
            )
        except Exception:
            state=self._journal.mark_unknown(draft.client_order_id,at=at)
            return MultiMarketPaperSubmissionOutcome(
                draft.market_lane,
                state.stage,
                "UNCERTAIN ALPACA PAPER POST: provider lookup required before any new execution",
                state,
                True,
            )

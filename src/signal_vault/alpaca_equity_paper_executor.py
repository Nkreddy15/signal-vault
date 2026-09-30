"""Alpaca US-equity PAPER-only one-shot entry adapter.

Hardcoded to paper-api.alpaca.markets.  No live host string or host override
exists.  A durable MultiMarketOrderDraft must already be approved and is
committed to SUBMISSION_PENDING before the one network POST attempt.
"""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Callable,Mapping
from urllib.request import Request,build_opener

from .alpaca_paper import PAPER_ROOT,_NoRedirects
from .cross_market_risk import assess_new_risk
from .multimarket_execution_journal import (
    MultiMarketExecutionJournal,MultiMarketOrderDraft,
)
from .paper_order_state import BrokerObservation,Stage

SYMBOLS=frozenset({"AAPL","AMD","MSFT","NVDA","QQQ","SPY"})
ORDER_PATH="/v2/orders"

def build_equity_paper_buy_draft(
    *,
    symbol:str,
    notional_usd:Decimal,
    client_order_id:str,
    exposure_by_lane:Mapping[str,Decimal],
    open_positions:int,
    marked_equity_usd:Decimal,
    daily_anchor_equity_usd:Decimal,
    peak_equity_usd:Decimal,
    operator_halted:bool,
) -> MultiMarketOrderDraft:
    if symbol not in SYMBOLS:
        raise ValueError("equity paper symbol not in predeclared research universe")
    if (type(notional_usd) is not Decimal or not notional_usd.is_finite() or
            notional_usd>=Decimal("10.01") or notional_usd<Decimal("1") or
            notional_usd!=notional_usd.quantize(Decimal("0.01"))):
        raise ValueError("equity paper notional must be exact cents from $1 to $10")
    risk=assess_new_risk(
        lane="us_equity",proposed_max_loss_usd=notional_usd,
        exposure_by_lane=exposure_by_lane,open_positions=open_positions,
        marked_equity_usd=marked_equity_usd,
        daily_anchor_equity_usd=daily_anchor_equity_usd,
        peak_equity_usd=peak_equity_usd,operator_halted=operator_halted)
    if not risk["risk_admissible"]:
        raise PermissionError("cross-market risk governor rejected equity entry")
    payload={
        "symbol":symbol,"side":"buy","type":"market","time_in_force":"day",
        "notional":format(notional_usd,"f"),"client_order_id":client_order_id,
    }
    return MultiMarketOrderDraft(
        client_order_id=client_order_id,market_lane="us_equity",
        instrument=symbol,max_loss_usd=notional_usd,payload=payload)

def _post_equity_paper(
    payload:Mapping[str,str],key:str,secret:str,
) -> Mapping[str,object]:
    if not key.strip() or not secret.strip():
        raise ValueError("separate Alpaca PAPER credentials required")
    if (set(payload)!={"symbol","side","type","time_in_force","notional","client_order_id"} or
            payload.get("symbol") not in SYMBOLS or payload.get("side")!="buy" or
            payload.get("type")!="market" or payload.get("time_in_force")!="day"):
        raise ValueError("unsupported equity paper payload")
    request=Request(
        PAPER_ROOT+ORDER_PATH,method="POST",
        data=json.dumps(dict(payload),separators=(",",":")).encode(),
        headers={
            "APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret,
            "Accept":"application/json","Content-Type":"application/json",
            "User-Agent":"SignalVault/0.3",
        })
    with build_opener(_NoRedirects).open(request,timeout=12) as response:
        raw=response.read(1_000_001)
    if len(raw)>1_000_000:
        raise ValueError("equity paper response too large")
    value=json.loads(raw)
    if not isinstance(value,dict):
        raise ValueError("invalid equity paper order response")
    return value

Transport=Callable[[Mapping[str,str],str,str],Mapping[str,object]]

class EquityPaperOnceExecutor:
    def __init__(
        self,*,paper_key:str,paper_secret:str,
        journal:MultiMarketExecutionJournal,
        transport:Transport=_post_equity_paper,
    ) -> None:
        if not paper_key.strip() or not paper_secret.strip():
            raise ValueError("paper credentials required")
        self.key,self.secret=paper_key,paper_secret
        self.journal,self.transport=journal,transport

    def submit_once(
        self,draft:MultiMarketOrderDraft,*,at:datetime,
    ) -> Stage:
        if draft.market_lane!="us_equity" or draft.instrument not in SYMBOLS:
            raise ValueError("not an approved equity paper draft")
        self.journal.begin_submission(draft,at=at)
        try:
            response=self.transport(draft.payload,self.key,self.secret)
            if response.get("client_order_id")!=draft.client_order_id:
                raise ValueError("equity provider client id mismatch")
            broker_id=response.get("id")
            status=response.get("status")
            if not isinstance(broker_id,str) or not broker_id or not isinstance(status,str):
                raise ValueError("invalid equity provider order identity/status")
            qty=Decimal(str(response.get("filled_qty","0")))
            avg=response.get("filled_avg_price")
            px=Decimal(str(avg)) if avg is not None else None
            state=self.journal.observe_provider(BrokerObservation(
                draft.client_order_id,broker_id,status,qty,px),at=at)
            return state.stage
        except Exception:
            return self.journal.mark_unknown(draft.client_order_id,at=at).stage

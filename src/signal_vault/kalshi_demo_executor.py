"""Kalshi DEMO-only one-shot order adapter.

The adapter is hardcoded to the Kalshi demo host and has no production host
constant.  Authentication is injected as a signing callback so private-key
material never enters the durable draft/journal.  Only small limit BID entries
are supported in this first execution drill.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from decimal import Decimal
from typing import Callable,Mapping
from urllib.parse import urlparse
from urllib.request import Request,urlopen

from .cross_market_risk import assess_new_risk
from .multimarket_execution_journal import (
    MultiMarketExecutionJournal,MultiMarketOrderDraft,
)
from .paper_order_state import BrokerObservation,Stage

DEMO_ROOT="https://external-api.demo.kalshi.co/trade-api/v2"
ORDER_PATH="/portfolio/events/orders"
Signer=Callable[[str,str,str],str]

def build_kalshi_demo_bid_draft(
    *,
    ticker:str,price:Decimal,count:Decimal,client_order_id:str,
    exposure_by_lane:Mapping[str,Decimal],open_positions:int,
    marked_equity_usd:Decimal,daily_anchor_equity_usd:Decimal,
    peak_equity_usd:Decimal,operator_halted:bool,
) -> MultiMarketOrderDraft:
    if (not isinstance(ticker,str) or not 1<=len(ticker)<=128 or
            any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in ticker)):
        raise ValueError("invalid Kalshi ticker")
    if (type(price) is not Decimal or not price.is_finite() or
            price<Decimal("0.01") or price>Decimal("0.99") or
            price!=price.quantize(Decimal("0.0001"))):
        raise ValueError("Kalshi demo price must be 0.0100-0.9900")
    if (type(count) is not Decimal or not count.is_finite() or count<=0 or
            count!=count.quantize(Decimal("0.01"))):
        raise ValueError("Kalshi demo count requires positive 0.01-contract precision")
    max_loss=price*count
    if max_loss>Decimal("10"):
        raise ValueError("Kalshi demo entry exceeds $10 maximum loss")
    risk=assess_new_risk(
        lane="kalshi_event_contract",proposed_max_loss_usd=max_loss,
        exposure_by_lane=exposure_by_lane,open_positions=open_positions,
        marked_equity_usd=marked_equity_usd,
        daily_anchor_equity_usd=daily_anchor_equity_usd,
        peak_equity_usd=peak_equity_usd,operator_halted=operator_halted)
    if not risk["risk_admissible"]:
        raise PermissionError("cross-market risk governor rejected Kalshi entry")
    payload={
        "ticker":ticker,"side":"bid","count":format(count,"f"),
        "price":format(price,"f"),"time_in_force":"good_till_canceled",
        "self_trade_prevention_type":"taker_at_cross",
        "client_order_id":client_order_id,
    }
    return MultiMarketOrderDraft(
        client_order_id=client_order_id,market_lane="kalshi_event_contract",
        instrument=ticker,max_loss_usd=max_loss,payload=payload)

def _post_demo(
    payload:Mapping[str,str],api_key_id:str,signer:Signer,
) -> Mapping[str,object]:
    if not api_key_id.strip():
        raise ValueError("Kalshi DEMO API key id required")
    parsed=urlparse(DEMO_ROOT)
    if parsed.scheme!="https" or parsed.hostname!="external-api.demo.kalshi.co":
        raise ValueError("Kalshi demo host invariant violated")
    stamp=str(int(time.time()*1000))
    sign_path="/trade-api/v2"+ORDER_PATH
    signature=signer(stamp,"POST",sign_path)
    if not isinstance(signature,str) or not signature:
        raise ValueError("Kalshi demo signer returned empty signature")
    request=Request(
        DEMO_ROOT+ORDER_PATH,method="POST",
        data=json.dumps(dict(payload),separators=(",",":")).encode(),
        headers={
            "KALSHI-ACCESS-KEY":api_key_id,
            "KALSHI-ACCESS-TIMESTAMP":stamp,
            "KALSHI-ACCESS-SIGNATURE":signature,
            "Accept":"application/json","Content-Type":"application/json",
            "User-Agent":"SignalVault/0.3",
        })
    with urlopen(request,timeout=12) as response:
        raw=response.read(1_000_001)
    if len(raw)>1_000_000:
        raise ValueError("Kalshi demo response too large")
    value=json.loads(raw)
    if not isinstance(value,dict):
        raise ValueError("invalid Kalshi demo response")
    return value

Transport=Callable[[Mapping[str,str],str,Signer],Mapping[str,object]]

class KalshiDemoOnceExecutor:
    def __init__(
        self,*,api_key_id:str,signer:Signer,
        journal:MultiMarketExecutionJournal,
        transport:Transport=_post_demo,
    ) -> None:
        if not api_key_id.strip() or not callable(signer):
            raise ValueError("Kalshi demo credentials/signer required")
        self.api_key_id,self.signer=api_key_id,signer
        self.journal,self.transport=journal,transport

    def submit_once(self,draft:MultiMarketOrderDraft,*,at:datetime) -> Stage:
        if draft.market_lane!="kalshi_event_contract":
            raise ValueError("not a Kalshi demo draft")
        self.journal.begin_submission(draft,at=at)
        try:
            response=self.transport(draft.payload,self.api_key_id,self.signer)
            order=response.get("order",response)
            if not isinstance(order,Mapping):
                raise ValueError("invalid Kalshi demo order response")
            broker_id=order.get("order_id")
            if not isinstance(broker_id,str) or not broker_id:
                raise ValueError("Kalshi demo order id missing")
            # Create response proves provider receipt, not a fill. Reconciliation
            # must use a later authenticated GET before this can become terminal.
            state=self.journal.observe_provider(BrokerObservation(
                draft.client_order_id,broker_id,"accepted",Decimal("0"),None),at=at)
            return state.stage
        except Exception:
            return self.journal.mark_unknown(draft.client_order_id,at=at).stage

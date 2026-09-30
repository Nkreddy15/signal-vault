"""Kalshi V2 DEMO authenticated request contract.

Builds the exact pre-sign message and authenticated headers for Kalshi demo
orders using an injected signing function. This module does not load private
keys, open files, send network requests, or support the production host.

Current Kalshi docs require:
timestamp_ms + uppercase HTTP method + full path without query parameters.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from .multimarket_paper_router import (
    KALSHI_DEMO_ROOT,
    KALSHI_ORDER_PATH,
    KALSHI_DEMO_ACK,
    PaperExecutionRoute,
    paper_submission_authorized,
)

Signer=Callable[[str],str]


@dataclass(frozen=True)
class KalshiDemoSignedRequest:
    method:str
    url:str
    path:str
    timestamp_ms:str
    headers:dict[str,str]
    payload:dict[str,str]

    def as_dict(self)->dict[str,object]:
        return {
            "method":self.method,
            "url":self.url,
            "path":self.path,
            "timestamp_ms":self.timestamp_ms,
            "headers":{
                "KALSHI-ACCESS-KEY":"<redacted>",
                "KALSHI-ACCESS-SIGNATURE":"<redacted>",
                "KALSHI-ACCESS-TIMESTAMP":self.timestamp_ms,
                "Content-Type":"application/json",
            },
            "payload":dict(self.payload),
            "live_trading":"UNAVAILABLE",
        }


def build_kalshi_demo_signed_order_request(
    route:PaperExecutionRoute,
    *,
    key_id:str,
    timestamp_ms:int,
    signer:Signer,
    acknowledgement:str,
)->KalshiDemoSignedRequest:
    if (
        route.provider!="kalshi"
        or route.environment!="demo"
        or route.endpoint!=KALSHI_DEMO_ROOT+KALSHI_ORDER_PATH
        or route.adapter!="kalshi_v2_demo_signed_order"
    ):
        raise PermissionError("exact Kalshi V2 demo route required")
    if acknowledgement!=KALSHI_DEMO_ACK or not paper_submission_authorized(
        route,acknowledgement
    ):
        raise PermissionError("exact Kalshi demo acknowledgement required")
    if not isinstance(key_id,str) or not key_id.strip() or key_id!=key_id.strip():
        raise ValueError("Kalshi demo key id required")
    if type(timestamp_ms) is not int or timestamp_ms<=0:
        raise ValueError("positive integer Kalshi timestamp milliseconds required")
    if not callable(signer):
        raise TypeError("Kalshi signer callback required")

    stamp=str(timestamp_ms)
    method="POST"
    path=KALSHI_ORDER_PATH
    presign=stamp+method+path
    signature=signer(presign)
    if not isinstance(signature,str) or not signature.strip():
        raise ValueError("Kalshi signer returned empty signature")

    return KalshiDemoSignedRequest(
        method=method,
        url=KALSHI_DEMO_ROOT+path,
        path=path,
        timestamp_ms=stamp,
        headers={
            "KALSHI-ACCESS-KEY":key_id,
            "KALSHI-ACCESS-SIGNATURE":signature,
            "KALSHI-ACCESS-TIMESTAMP":stamp,
            "Content-Type":"application/json",
        },
        payload=dict(route.payload),
    )

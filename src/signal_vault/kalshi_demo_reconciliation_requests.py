"""No-network Kalshi DEMO authenticated GET request builders.

Builds strict signed requests for one order and its fills. Query parameters are
included in the URL but excluded from the pre-sign path, matching Kalshi's
authentication contract. No private-key loading or network I/O occurs here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote, urlencode

from .multimarket_paper_router import KALSHI_DEMO_ROOT

Signer=Callable[[str],str]
_ORDER_PREFIX="/trade-api/v2/portfolio/orders/"
_FILLS_PATH="/trade-api/v2/portfolio/fills"


@dataclass(frozen=True)
class KalshiDemoSignedGet:
    url:str
    path_for_signature:str
    timestamp_ms:str
    headers:dict[str,str]

    def as_dict(self)->dict[str,object]:
        return {
            "method":"GET",
            "url":self.url,
            "path_for_signature":self.path_for_signature,
            "timestamp_ms":self.timestamp_ms,
            "headers":{
                "KALSHI-ACCESS-KEY":"<redacted>",
                "KALSHI-ACCESS-SIGNATURE":"<redacted>",
                "KALSHI-ACCESS-TIMESTAMP":self.timestamp_ms,
            },
            "live_trading":"UNAVAILABLE",
        }


def _clean_id(value:str,*,name:str)->str:
    if (
        not isinstance(value,str) or not value or len(value)>160
        or any(ch.isspace() or ord(ch)<33 or ord(ch)>126 for ch in value)
    ):
        raise ValueError(f"invalid Kalshi {name}")
    return value


def _signed_get(
    *,
    path:str,
    query:dict[str,str|int]|None,
    key_id:str,
    timestamp_ms:int,
    signer:Signer,
)->KalshiDemoSignedGet:
    if not path.startswith("/trade-api/v2/portfolio/") or "?" in path:
        raise ValueError("Kalshi signed GET path escaped portfolio allowlist")
    if not isinstance(key_id,str) or not key_id.strip() or key_id!=key_id.strip():
        raise ValueError("Kalshi demo key id required")
    if type(timestamp_ms) is not int or timestamp_ms<=0:
        raise ValueError("positive integer Kalshi timestamp milliseconds required")
    if not callable(signer):
        raise TypeError("Kalshi signer callback required")
    stamp=str(timestamp_ms)
    presign=stamp+"GET"+path
    signature=signer(presign)
    if not isinstance(signature,str) or not signature.strip():
        raise ValueError("Kalshi signer returned empty signature")
    suffix=("?"+urlencode(query)) if query else ""
    return KalshiDemoSignedGet(
        url=KALSHI_DEMO_ROOT+path+suffix,
        path_for_signature=path,
        timestamp_ms=stamp,
        headers={
            "KALSHI-ACCESS-KEY":key_id,
            "KALSHI-ACCESS-SIGNATURE":signature,
            "KALSHI-ACCESS-TIMESTAMP":stamp,
        },
    )


def build_kalshi_demo_order_lookup(
    *,
    order_id:str,
    key_id:str,
    timestamp_ms:int,
    signer:Signer,
)->KalshiDemoSignedGet:
    order=_clean_id(order_id,name="order id")
    path=_ORDER_PREFIX+quote(order,safe="-._")
    return _signed_get(
        path=path,query=None,key_id=key_id,
        timestamp_ms=timestamp_ms,signer=signer,
    )


def build_kalshi_demo_fills_lookup(
    *,
    order_id:str,
    key_id:str,
    timestamp_ms:int,
    signer:Signer,
    limit:int=1000,
)->KalshiDemoSignedGet:
    order=_clean_id(order_id,name="order id")
    if type(limit) is not int or not 1<=limit<=1000:
        raise ValueError("Kalshi fills limit must be 1-1000")
    return _signed_get(
        path=_FILLS_PATH,
        query={"order_id":order,"limit":limit},
        key_id=key_id,timestamp_ms=timestamp_ms,signer=signer,
    )

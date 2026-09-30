"""Strict GET-only Kalshi public/historical research adapter.

No Kalshi credentials are read.  No POST/PUT/PATCH/DELETE method exists.
The adapter is intentionally limited to public market metadata, trades and
historical endpoints so research can be accelerated with past resolved data
without creating any trading authority.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

PRODUCTION_PUBLIC_BASE="https://external-api.kalshi.com/trade-api/v2"
MAX_RESPONSE_BYTES=8_000_000
MAX_LIMIT=1000
ALLOWED_HOSTS=frozenset({"external-api.kalshi.com","api.elections.kalshi.com"})

Transport=Callable[[Request,float], bytes]

def _default_transport(request:Request,timeout:float) -> bytes:
    with urlopen(request,timeout=timeout) as response:
        data=response.read(MAX_RESPONSE_BYTES+1)
    return data

@dataclass(frozen=True)
class KalshiPublicResearchClient:
    base_url:str=PRODUCTION_PUBLIC_BASE
    timeout_seconds:float=15.0
    transport:Transport=_default_transport

    def __post_init__(self) -> None:
        parsed=urlparse(self.base_url)
        if (parsed.scheme!="https" or parsed.hostname not in ALLOWED_HOSTS or
                parsed.path.rstrip("/")!="/trade-api/v2" or parsed.query or parsed.fragment):
            raise ValueError("Kalshi research base URL is not allowlisted")
        if not 1.0<=self.timeout_seconds<=30.0:
            raise ValueError("bounded Kalshi timeout required")

    def _get(self,path:str,params:dict[str,object]|None=None) -> dict[str,object]:
        if not path.startswith("/") or ".." in path or "://" in path:
            raise ValueError("invalid Kalshi path")
        query=""
        if params:
            cleaned={}
            for key,value in params.items():
                if value is None:
                    continue
                if not isinstance(key,str) or not key.replace("_","").isalnum():
                    raise ValueError("invalid Kalshi query key")
                if isinstance(value,(str,int,bool)):
                    cleaned[key]=str(value).lower() if isinstance(value,bool) else str(value)
                else:
                    raise ValueError("invalid Kalshi query value")
            query="?"+urlencode(cleaned) if cleaned else ""
        url=self.base_url.rstrip("/")+path+query
        request=Request(url,headers={"Accept":"application/json"},method="GET")
        body=self.transport(request,self.timeout_seconds)
        if not isinstance(body,(bytes,bytearray)) or not body or len(body)>MAX_RESPONSE_BYTES:
            raise ValueError("invalid or oversized Kalshi response")
        try:
            decoded=json.loads(bytes(body))
        except (UnicodeDecodeError,json.JSONDecodeError) as exc:
            raise ValueError("Kalshi response is not valid JSON") from exc
        if not isinstance(decoded,dict):
            raise ValueError("Kalshi response must be a JSON object")
        return decoded

    def historical_cutoff(self) -> dict[str,object]:
        return self._get("/historical/cutoff")

    def historical_markets(
        self,*,limit:int=1000,cursor:str|None=None,
        series_ticker:str|None=None,event_ticker:str|None=None,
    ) -> dict[str,object]:
        if type(limit) is not int or not 1<=limit<=MAX_LIMIT:
            raise ValueError("Kalshi historical market limit out of bounds")
        if series_ticker and event_ticker:
            raise ValueError("use one Kalshi historical market scope at a time")
        return self._get("/historical/markets",{
            "limit":limit,"cursor":cursor,
            "series_ticker":series_ticker,"event_ticker":event_ticker,
            "mve_filter":"exclude",
        })

    def historical_trades(
        self,*,ticker:str|None=None,min_ts:int|None=None,max_ts:int|None=None,
        limit:int=1000,cursor:str|None=None,
    ) -> dict[str,object]:
        if type(limit) is not int or not 1<=limit<=MAX_LIMIT:
            raise ValueError("Kalshi historical trade limit out of bounds")
        for value in (min_ts,max_ts):
            if value is not None and (type(value) is not int or value<0):
                raise ValueError("Kalshi timestamp must be nonnegative integer seconds")
        if min_ts is not None and max_ts is not None and min_ts>max_ts:
            raise ValueError("Kalshi historical time bounds reversed")
        return self._get("/historical/trades",{
            "ticker":ticker,"min_ts":min_ts,"max_ts":max_ts,
            "limit":limit,"cursor":cursor,
        })

    def historical_market_candlesticks(
        self,*,ticker:str,start_ts:int,end_ts:int,period_interval:int=60,
    ) -> dict[str,object]:
        if (not isinstance(ticker,str) or not ticker or len(ticker)>128 or
                any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in ticker)):
            raise ValueError("invalid Kalshi market ticker")
        if (type(start_ts) is not int or type(end_ts) is not int or
                start_ts<0 or end_ts<=start_ts):
            raise ValueError("invalid Kalshi candlestick time bounds")
        if period_interval not in {1,60,1440}:
            raise ValueError("unsupported Kalshi candlestick interval")
        return self._get(
            f"/historical/markets/{ticker}/candlesticks",
            {"start_ts":start_ts,"end_ts":end_ts,
             "period_interval":period_interval},
        )

    def collect_historical_trades(
        self,*,ticker:str|None=None,min_ts:int|None=None,max_ts:int|None=None,
        max_pages:int=50,
    ) -> tuple[dict[str,object],...]:
        if type(max_pages) is not int or not 1<=max_pages<=200:
            raise ValueError("bounded Kalshi page count required")
        pages=[]
        cursor=None
        for _ in range(max_pages):
            page=self.historical_trades(
                ticker=ticker,min_ts=min_ts,max_ts=max_ts,
                limit=MAX_LIMIT,cursor=cursor)
            pages.append(page)
            next_cursor=page.get("cursor")
            if next_cursor in (None,""):
                return tuple(pages)
            if not isinstance(next_cursor,str) or len(next_cursor)>4096:
                raise ValueError("invalid Kalshi cursor")
            cursor=next_cursor
        raise ValueError("Kalshi historical pagination exceeded bound")

    def live_public_markets(
        self,*,status:str="open",limit:int=1000,cursor:str|None=None,
    ) -> dict[str,object]:
        if status not in {"unopened","open","paused","closed","settled"}:
            raise ValueError("invalid Kalshi public market status")
        if type(limit) is not int or not 1<=limit<=MAX_LIMIT:
            raise ValueError("Kalshi market limit out of bounds")
        return self._get("/markets",{
            "status":status,"limit":limit,"cursor":cursor,"mve_filter":"exclude",
        })

def research_safety_receipt() -> dict[str,object]:
    return {
        "kind":"KALSHI_PUBLIC_HISTORICAL_RESEARCH_ADAPTER",
        "network_method_allowlist":["GET"],
        "credentials_accessed":"NONE",
        "authenticated_portfolio_access":"DISABLED",
        "broker_order_submission":"DISABLED",
        "demo_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }

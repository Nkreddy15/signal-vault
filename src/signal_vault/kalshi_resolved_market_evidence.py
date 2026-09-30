"""Bounded immutable evidence capture for one historical Kalshi market.

This captures public historical candlesticks and paginated trades for an exact
market ticker. It uses the existing GET-only public research client and never
reads credentials, signs requests, accesses a portfolio, or submits orders.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Protocol

from .kalshi_public_research import KalshiPublicResearchClient

MAX_TRADE_PAGES=50
MAX_WINDOW_SECONDS=60*60*24*120


class ResolvedMarketClient(Protocol):
    def historical_market(self,ticker:str) -> dict[str,object]: ...
    def historical_market_candlesticks(
        self,*,ticker:str,start_ts:int,end_ts:int,period_interval:int=60,
    ) -> dict[str,object]: ...
    def historical_trades(
        self,*,ticker:str|None=None,min_ts:int|None=None,max_ts:int|None=None,
        limit:int=1000,cursor:str|None=None,
    ) -> dict[str,object]: ...


def _validate_ticker(ticker:str)->str:
    if (
        not isinstance(ticker,str) or not ticker or len(ticker)>128
        or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in ticker)
    ):
        raise ValueError("invalid Kalshi historical market ticker")
    return ticker


def _new_private_root(root:Path)->None:
    if root.exists() or root.is_symlink():
        raise ValueError("Kalshi resolved-market output root must be new")
    root.mkdir(mode=0o700)
    if root.stat().st_mode & 0o077:
        raise PermissionError("Kalshi resolved-market output root must be private")


def _write(path:Path,obj:dict[str,object])->str:
    raw=(json.dumps(obj,sort_keys=True,separators=(",",":"))+"\n").encode()
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
    if hasattr(os,"O_NOFOLLOW"):
        flags|=os.O_NOFOLLOW
    fd=os.open(path,flags,0o600)
    with os.fdopen(fd,"wb") as fh:
        os.fchmod(fh.fileno(),0o600)
        fh.write(raw)
        fh.flush()
        os.fsync(fh.fileno())
    return hashlib.sha256(raw).hexdigest()


def capture_resolved_market_evidence(
    *,
    client:ResolvedMarketClient,
    ticker:str,
    start_ts:int,
    end_ts:int,
    output_root:Path,
    max_trade_pages:int=10,
    candlestick_interval:int=60,
)->dict[str,object]:
    ticker=_validate_ticker(ticker)
    if (
        type(start_ts) is not int or type(end_ts) is not int
        or start_ts<0 or end_ts<=start_ts
        or end_ts-start_ts>MAX_WINDOW_SECONDS
    ):
        raise ValueError("bounded historical Kalshi time window required")
    if type(max_trade_pages) is not int or not 1<=max_trade_pages<=MAX_TRADE_PAGES:
        raise ValueError("bounded historical Kalshi trade page count required")
    if candlestick_interval not in {1,60,1440}:
        raise ValueError("unsupported Kalshi candlestick interval")

    _new_private_root(output_root)

    metadata=client.historical_market(ticker)
    market=metadata.get("market") if isinstance(metadata,dict) else None
    if not isinstance(market,dict):
        raise ValueError("Kalshi historical market metadata missing market object")
    if market.get("ticker")!=ticker:
        raise ValueError("Kalshi historical market metadata ticker mismatch")
    result=market.get("result")
    if result not in {"yes","no"}:
        raise ValueError("Kalshi historical market must have binary settled result")
    if market.get("status") not in {"settled","closed"}:
        raise ValueError("Kalshi historical market is not resolved")
    settlement_ts=market.get("settlement_ts")
    if not isinstance(settlement_ts,str) or not settlement_ts:
        raise ValueError("Kalshi resolved market is missing settlement timestamp")
    metadata_sha=_write(output_root/"market.json",metadata)

    candles=client.historical_market_candlesticks(
        ticker=ticker,
        start_ts=start_ts,
        end_ts=end_ts,
        period_interval=candlestick_interval,
    )
    candle_sha=_write(output_root/"candlesticks.json",candles)

    pages=[]
    cursor=None
    seen=set()
    for index in range(1,max_trade_pages+1):
        page=client.historical_trades(
            ticker=ticker,
            min_ts=start_ts,
            max_ts=end_ts,
            limit=1000,
            cursor=cursor,
        )
        sha=_write(output_root/f"trades-page-{index:03d}.json",page)
        pages.append({"page":index,"sha256":sha})
        next_cursor=page.get("cursor")
        if next_cursor in (None,""):
            cursor=None
            break
        if not isinstance(next_cursor,str) or not next_cursor or len(next_cursor)>4096:
            raise ValueError("invalid Kalshi historical trade cursor")
        if next_cursor in seen:
            raise ValueError("repeated Kalshi trade cursor would loop")
        seen.add(next_cursor)
        cursor=next_cursor
    else:
        if cursor is not None:
            raise ValueError("Kalshi historical trades exceeded requested page bound")

    manifest={
        "kind":"IMMUTABLE_KALSHI_RESOLVED_MARKET_PUBLIC_EVIDENCE",
        "ticker":ticker,
        "start_ts":start_ts,
        "end_ts":end_ts,
        "candlestick_interval":candlestick_interval,
        "market_metadata_sha256":metadata_sha,
        "resolved_result":result,
        "settlement_ts":settlement_ts,
        "candlesticks_sha256":candle_sha,
        "trade_pages":pages,
        "credentials_accessed":"NONE",
        "authenticated_portfolio_access":"DISABLED",
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
    }
    manifest_sha=_write(output_root/"manifest.json",manifest)
    return {**manifest,"manifest_sha256":manifest_sha}


def main(argv:list[str]|None=None)->int:
    import argparse
    parser=argparse.ArgumentParser(
        description="Public GET-only Kalshi resolved-market evidence capture"
    )
    parser.add_argument("--ticker",required=True)
    parser.add_argument("--start-ts",required=True,type=int)
    parser.add_argument("--end-ts",required=True,type=int)
    parser.add_argument("--max-trade-pages",type=int,default=10)
    parser.add_argument("--candlestick-interval",type=int,default=60)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        result=capture_resolved_market_evidence(
            client=KalshiPublicResearchClient(),
            ticker=args.ticker,
            start_ts=args.start_ts,
            end_ts=args.end_ts,
            output_root=args.output,
            max_trade_pages=args.max_trade_pages,
            candlestick_interval=args.candlestick_interval,
        )
        print(json.dumps(result,sort_keys=True,indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "kind":"KALSHI_RESOLVED_MARKET_PUBLIC_EVIDENCE",
            "status":"FAIL_CLOSED",
            "failure_class":type(exc).__name__,
            "credentials_accessed":"NONE",
            "order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        },sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())

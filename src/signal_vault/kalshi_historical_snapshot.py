"""Immutable bounded Kalshi historical market-catalog snapshots.

Uses only the existing public GET-only Kalshi research client. No API keys,
signatures, portfolio endpoints, order methods, or live trading capabilities
exist in this module.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Protocol

from .kalshi_public_research import KalshiPublicResearchClient

ROOT=Path("private-kalshi-historical-artifacts")
MAX_PAGES=20


class HistoricalClient(Protocol):
    def historical_cutoff(self) -> dict[str,object]: ...
    def historical_markets(
        self,*,limit:int=1000,cursor:str|None=None,
        series_ticker:str|None=None,event_ticker:str|None=None,
    ) -> dict[str,object]: ...


def _private_new_root(root:Path)->None:
    if root.exists() or root.is_symlink():
        raise ValueError("Kalshi historical output root must be new")
    root.mkdir(mode=0o700)
    if root.stat().st_mode & 0o077:
        raise PermissionError("Kalshi historical output root must be private")


def _write_once(path:Path,payload:dict[str,object])->str:
    raw=(json.dumps(payload,sort_keys=True,separators=(",",":"))+"\n").encode()
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


def collect_historical_market_catalog(
    *,
    client:HistoricalClient,
    output_root:Path=ROOT,
    max_pages:int=10,
    series_ticker:str|None=None,
    event_ticker:str|None=None,
)->dict[str,object]:
    if type(max_pages) is not int or not 1<=max_pages<=MAX_PAGES:
        raise ValueError("bounded Kalshi historical page count required")
    if series_ticker and event_ticker:
        raise ValueError("use at most one Kalshi catalog scope")
    for value in (series_ticker,event_ticker):
        if value is not None and (
            not isinstance(value,str) or not value or len(value)>128
            or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in value)
        ):
            raise ValueError("invalid Kalshi historical scope ticker")

    _private_new_root(output_root)
    cutoff=client.historical_cutoff()
    cutoff_sha=_write_once(output_root/"historical_cutoff.json",cutoff)

    pages=[]
    cursor=None
    seen=set()
    for index in range(1,max_pages+1):
        page=client.historical_markets(
            limit=1000,
            cursor=cursor,
            series_ticker=series_ticker,
            event_ticker=event_ticker,
        )
        sha=_write_once(output_root/f"markets-page-{index:03d}.json",page)
        pages.append({"page":index,"sha256":sha})
        next_cursor=page.get("cursor")
        if next_cursor in (None,""):
            cursor=None
            break
        if not isinstance(next_cursor,str) or not next_cursor or len(next_cursor)>4096:
            raise ValueError("invalid Kalshi historical catalog cursor")
        if next_cursor in seen:
            raise ValueError("repeated Kalshi cursor would loop")
        seen.add(next_cursor)
        cursor=next_cursor
    else:
        if cursor is not None:
            raise ValueError("Kalshi historical catalog exceeded requested page bound")

    manifest={
        "kind":"IMMUTABLE_KALSHI_PUBLIC_HISTORICAL_MARKET_CATALOG",
        "source":"kalshi_public_historical_GET_only",
        "cutoff_sha256":cutoff_sha,
        "market_pages":pages,
        "series_ticker":series_ticker,
        "event_ticker":event_ticker,
        "credentials_accessed":"NONE",
        "authenticated_portfolio_access":"DISABLED",
        "broker_order_submission":"DISABLED",
        "demo_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
    manifest_sha=_write_once(output_root/"manifest.json",manifest)
    return {**manifest,"manifest_sha256":manifest_sha}


def main(argv:list[str]|None=None)->int:
    import argparse
    parser=argparse.ArgumentParser(
        description="Public GET-only bounded Kalshi historical catalog snapshot"
    )
    parser.add_argument("--max-pages",type=int,default=10)
    parser.add_argument("--series-ticker")
    parser.add_argument("--event-ticker")
    parser.add_argument("--output",type=Path,default=ROOT)
    args=parser.parse_args(argv)
    try:
        result=collect_historical_market_catalog(
            client=KalshiPublicResearchClient(),
            output_root=args.output,
            max_pages=args.max_pages,
            series_ticker=args.series_ticker,
            event_ticker=args.event_ticker,
        )
        print(json.dumps(result,sort_keys=True,indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "kind":"KALSHI_PUBLIC_HISTORICAL_MARKET_CATALOG",
            "status":"FAIL_CLOSED",
            "failure_class":type(exc).__name__,
            "credentials_accessed":"NONE",
            "order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        },sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())

"""Operator-controlled historical multi-asset research CLI. NO order commands.

The default --dry-run uses zero credentials and zero network requests.
An explicit --download-history historical DATA GET prompts privately for a
dedicated PAPER DATA pair; keys never enter argv, source, JSON, GitHub or
Railway configuration. It does NOT touch the deployed BTC forward root.

--offline-report re-checks the archived SHA and needs no API access at all.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence

from .multi_asset_historical import (
    BoundedAlpacaHistoricalBatch, MAX_SYMBOLS, archive_historical_batch,
)
from .multi_asset_simulation import ExplicitRoundTripCosts, ResearchHypothesis
from .offline_multimarket_pipeline import (
    combine_historical_archives, describe_multi_asset_research,
    read_historical_archive,
)
from .research_universe import AssetClass, candidate

CHUNK=timedelta(days=14)
MAX_CHUNKS=30


def aware(raw: str) -> datetime:
    if not isinstance(raw,str) or len(raw)>64:
        raise ValueError("valid explicit ISO-8601 datetime required")
    stamp=datetime.fromisoformat(raw.replace("Z","+00:00"))
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("historical dataset bounds require explicit timezone")
    return stamp.astimezone(timezone.utc)


def windows(start: datetime,end: datetime) -> tuple[tuple[datetime,datetime],...]:
    if start>=end:
        raise ValueError("nonempty historical interval required")
    pieces=[]
    now=start
    while now<end:
        nxt=min(now+CHUNK,end)
        pieces.append((now,nxt))
        if len(pieces)>MAX_CHUNKS:
            raise ValueError("maximum 30 bounded historical requests per invocation")
        now=nxt
    return tuple(pieces)


def _read_private_json(path: Path, *, limit: int=200_000) -> object:
    if (path.is_symlink() or not path.is_file() or
            path.stat().st_mode & 0o077 or
            not 0<path.stat().st_size<=limit):
        raise ValueError("research config must be a preexisting private 0600 JSON file")
    return json.loads(path.read_text(encoding="utf-8"))


def explicit_equity_bar_grid(
    path: Path, *, symbols: Sequence[str], feed: str,
) -> dict[str,tuple[datetime,...]]:
    payload=_read_private_json(path)
    if (not isinstance(payload,dict) or
            payload.get("kind")!="OPERATOR_REVIEWED_EQUITY_HOURLY_BAR_GRID"
            or payload.get("feed")!=feed or
            payload.get("reviewed_provider_timestamps") is not True or
            set(payload)!={
                "kind","feed","reviewed_provider_timestamps","symbols"} or
            not isinstance(payload.get("symbols"),dict) or
            set(payload["symbols"])!=set(symbols)):
        raise ValueError("explicit per-equity provider bar grid required")
    out={}
    for sym in symbols:
        data=payload["symbols"][sym]
        if not isinstance(data,list) or not data:
            raise ValueError("incomplete per-symbol provider candle grid")
        stamps=tuple(aware(v) for v in data)
        if (len(set(stamps))!=len(stamps) or stamps!=tuple(sorted(stamps))
                or any(t.second or t.microsecond for t in stamps)):
            raise ValueError("provider candle grid must be sorted minute-exact unique")
        out[sym]=stamps
    return out


def configured_costs(path: Path, *, symbols: Sequence[str]) -> dict[str,ExplicitRoundTripCosts]:
    payload=_read_private_json(path)
    if not isinstance(payload,dict) or set(payload)!=set(symbols):
        raise ValueError("one complete explicit cost model required per research symbol")
    out={}
    for sym in symbols:
        raw=payload[sym]
        if not isinstance(raw,dict) or set(raw)!={
                "taker_fee_bps","full_spread_bps","slippage_per_side_bps"}:
            raise ValueError("cost model fields missing or unexpected")
        out[sym]=ExplicitRoundTripCosts(
            Decimal(str(raw["taker_fee_bps"])),
            Decimal(str(raw["full_spread_bps"])),
            Decimal(str(raw["slippage_per_side_bps"])))
    return out


def historical_plan(
    *, symbols: Sequence[str],start: datetime,end: datetime,
    market: AssetClass,equity_feed: str | None=None,
) -> dict[str,object]:
    items=tuple(candidate(sym) for sym in symbols)
    if (not 1<=len(items)<=MAX_SYMBOLS or
            len({x.symbol for x in items})!=len(items) or
            any(x.asset_class!=market for x in items)):
        raise ValueError("1-6 unique candidate symbols from ONE asset class required")
    if market==AssetClass.US_EQUITY and equity_feed not in ("iex","sip"):
        raise ValueError("must select explicitly entitled iex/sip equity feed")
    if market==AssetClass.CRYPTO and equity_feed is not None:
        raise ValueError("crypto plan does not use equity feed")
    if (start.second or start.microsecond or end.second or end.microsecond or
            (market==AssetClass.CRYPTO and (start.minute or end.minute))):
        raise ValueError("historical request boundary misalignment")
    plan=windows(start,end)
    return {
        "kind":"OFFLINE_PREDECLARED_HISTORICAL_GET_PLAN_NO_NETWORK",
        "market":market.value,
        "symbols":[a.symbol for a in items],
        "equity_feed":equity_feed,
        "window_count":len(plan),
        "windows":[{"start_utc":a.isoformat(),"end_utc":b.isoformat()}
                   for a,b in plan],
        "requests_triggered":0,
        "credential_access":"NONE",
        "broker_order_submission":"DISABLED",
        "data_classification":"HISTORICAL_NEVER_PROSPECTIVE",
    }


def download_history(
    *,
    symbols: Sequence[str],start: datetime,end: datetime,
    market:AssetClass,equity_feed:str | None,
    output_folder: Path,
    key_id: str,secret: str,
    provider_factory=BoundedAlpacaHistoricalBatch,
    equity_grid: Mapping[str,Sequence[datetime]] | None=None,
    now: datetime | None=None,
) -> dict[str,object]:
    """Explicit data-only activation; one prompted credential pair, bounded calls.

    Existing archive files remain unchanged if a later batch is incomplete or
    provider returns an error. Does not auto-resume or claim future evidence.
    """
    plan=historical_plan(
        symbols=symbols,start=start,end=end,market=market,equity_feed=equity_feed)
    checked=datetime.now(timezone.utc) if now is None else now.astimezone(timezone.utc)
    if end>checked:
        raise ValueError("cannot download an open/future historical window")
    root=Path(output_folder)
    if (root.is_symlink() or not root.is_dir() or
            root.stat().st_mode & 0o077 or
            root.resolve()==Path("/var/lib/signal-vault/forward")):
        raise ValueError("preexisting private 0700 independent historical folder required")
    grid={} if equity_grid is None else dict(equity_grid)
    if market==AssetClass.US_EQUITY and set(grid)!=set(symbols):
        raise ValueError("independently reviewed equity session bar grid required")
    if market==AssetClass.CRYPTO and grid:
        raise ValueError("no equity calendar permitted in crypto lane")
    # No secrets in reports, filenames, arg parser, logging or persistent files.
    cli=provider_factory(key_id,secret)
    reports=[]
    for bounds in plan["windows"]:
        a=aware(bounds["start_utc"])
        b=aware(bounds["end_utc"])
        cal=(None if market==AssetClass.CRYPTO else
             {sym:tuple(t for t in grid[sym] if a<=t and t+timedelta(hours=1)<=b)
              for sym in symbols})
        if cal is not None and any(not x for x in cal.values()):
            raise ValueError("empty per-asset equity calendar in one history window")
        batch=cli.fetch(
            specs=[candidate(sym) for sym in symbols],
            start=a,end=b,as_of=checked,equity_feed=equity_feed,
            equity_expected_open_minutes=cal)
        target=archive_historical_batch(batch,output_folder=root)
        reports.append({
            "archive_basename":target.name,
            "archive_sha256":hashlib.sha256(target.read_bytes()).hexdigest(),
            "per_symbol_historical_rows":{
                sym:len(rows) for sym,rows in batch.bars.items()},
            "page_count":batch.page_count,
            "prospective_observations_verified":0,
        })
    return {
        "kind":"OPERATOR_REQUESTED_HISTORICAL_MULTIASSET_GET_ARCHIVES",
        "completed_history_windows":len(reports),
        "results":reports,
        "credential_values_in_output":False,
        "historical_never_forward_observations":True,
        "broker_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


def run_offline_report(
    archive_paths: Sequence[Path],
    *,
    cost_config: Path,
    equity_calendar: Path | None=None,
    hypotheses: Sequence[ResearchHypothesis] | None=None,
) -> dict[str,object]:
    """No network, no credentials, no order/API imports."""
    if not archive_paths or len(archive_paths)>90:
        raise ValueError("provide 1-90 private historical archives")
    parts=tuple(read_historical_archive(p) for p in archive_paths)
    symbols=tuple(sorted({sym for part in parts for sym in part.symbols}))
    equity=tuple(sym for sym in symbols
                 if candidate(sym).asset_class==AssetClass.US_EQUITY)
    cal={}
    if equity:
        if equity_calendar is None:
            raise ValueError("separately reviewed stock hourly grid required")
        feeds={part.feed.split("_")[-1] for part in parts
               if part.asset_class=="us_equity"}
        if len(feeds)!=1:
            raise ValueError("cannot mix stock data feeds in one review")
        cal=explicit_equity_bar_grid(
            equity_calendar,symbols=equity,feed=next(iter(feeds)))
    elif equity_calendar is not None:
        raise ValueError("equity calendar supplied without stock assets")
    cutoff=max(aware(x.downloaded_utc) for x in parts)
    combined,reviews=combine_historical_archives(
        parts,as_of=cutoff,equity_calendars=cal)
    kwargs={}
    if hypotheses is not None:
        kwargs["hypotheses"]=tuple(hypotheses)
    result=describe_multi_asset_research(
        combined,as_of=cutoff,costs=configured_costs(
            cost_config,symbols=symbols),
        equity_calendars=cal,**kwargs)
    result["historical_archive_count"]=len(parts)
    result["per_symbol_quality_reviews"]=reviews
    result["network_requests"]="NONE"
    result["credential_access"]="NONE"
    return result


def main(argv: list[str] | None=None) -> int:
    p=argparse.ArgumentParser(
        description="Historical-only multi-asset GET/download/offline review; NO orders.")
    flags=p.add_mutually_exclusive_group(required=True)
    flags.add_argument("--dry-run",action="store_true",help="Print batch plan, NO network/credentials.")
    flags.add_argument("--download-history",action="store_true",
                       help="EXPLICIT historical DATA GET after private terminal prompts.")
    flags.add_argument("--offline-report",nargs="+",type=Path,
                       help="Read SHA-verifiable historical archives, no network or API secrets.")
    p.add_argument("--market",choices=("crypto","us_equity"))
    p.add_argument("--symbols",nargs="+",help="1-6 registry symbols, quote BTC/USD in shell.")
    p.add_argument("--start",help="Timezone-aware inclusive UTC ISO timestamp.")
    p.add_argument("--end",help="Timezone-aware exclusive UTC ISO timestamp.")
    p.add_argument("--equity-feed",choices=("iex","sip"))
    p.add_argument("--equity-calendar",type=Path)
    p.add_argument("--private-archive-folder",type=Path)
    p.add_argument("--costs-file",type=Path)
    args=p.parse_args(argv)
    if args.offline_report is not None:
        if args.costs_file is None:
            p.error("--offline-report requires --costs-file with explicit per-symbol estimates")
        result=run_offline_report(
            args.offline_report,cost_config=args.costs_file,
            equity_calendar=args.equity_calendar)
    else:
        if not all((args.market,args.symbols,args.start,args.end)):
            p.error("--market --symbols --start --end are required for historical plan")
        market=AssetClass(args.market)
        start,end=aware(args.start),aware(args.end)
        if args.dry_run:
            result=historical_plan(
                symbols=args.symbols,start=start,end=end,market=market,
                equity_feed=args.equity_feed)
        else:
            if args.private_archive_folder is None:
                p.error("--download-history requires existing private --private-archive-folder")
            equity_grid=None
            if market==AssetClass.US_EQUITY:
                if args.equity_calendar is None:
                    p.error("stock download requires a reviewed --equity-calendar")
                equity_grid=explicit_equity_bar_grid(
                    args.equity_calendar,symbols=args.symbols,feed=args.equity_feed)
            # Validate ALL nonsecret inputs before prompting for keys.
            historical_plan(
                symbols=args.symbols,start=start,end=end,market=market,
                equity_feed=args.equity_feed)
            key=getpass.getpass("Private Alpaca PAPER DATA Key ID (not echoed): ")
            secret=getpass.getpass("Private Alpaca PAPER DATA Secret (not echoed): ")
            result=download_history(
                symbols=args.symbols,start=start,end=end,market=market,
                equity_feed=args.equity_feed,
                output_folder=args.private_archive_folder,
                key_id=key,secret=secret,equity_grid=equity_grid)
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())

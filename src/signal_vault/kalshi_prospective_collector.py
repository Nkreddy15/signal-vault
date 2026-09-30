"""Precommitted prospective Kalshi GET-only market collector.

Selection uses only structural public metadata available before the fixed
decision horizons. It never uses YES/NO outcome direction, price level,
historical P&L, or later settlement to choose markets.

Each selected market is frozen before its 24h and 6h reference horizons.
At those horizons the collector may archive a bounded public quote snapshot.
Missed horizons are never backfilled as if prospective.

No credentials, portfolio endpoints, demo orders, or live orders are used.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping, Protocol

from .kalshi_public_research import KalshiPublicResearchClient
from .kalshi_reference_hypotheses import POLICY_VERSION as HYPOTHESIS_POLICY

PLAN_KIND="PRECOMMITTED_KALSHI_PROSPECTIVE_MARKET_PLAN_NO_ORDERS"
PLAN_POLICY="kalshi-prospective-market-plan-v1-predeclared-20260930"
SNAPSHOT_KIND="KALSHI_PROSPECTIVE_FIXED_HORIZON_PUBLIC_SNAPSHOT_NO_ORDERS"

DEFAULT_MARKET_COUNT=20
MIN_MARKET_COUNT=20
MIN_DISTINCT_EVENTS=10
MAX_MARKET_COUNT=50
MAX_DISCOVERY_PAGES=10
MAX_CLOSE_AHEAD_DAYS=30
MIN_PLAN_LEAD_HOURS=25
HORIZONS=(86400,21600)
CAPTURE_WINDOW=timedelta(minutes=60)


class ProspectiveClient(Protocol):
    def live_public_markets(
        self,*,status:str="open",limit:int=1000,cursor:str|None=None,
    )->dict[str,object]: ...
    def live_public_market(self,ticker:str)->dict[str,object]: ...


def _utc(value:datetime)->datetime:
    if (
        not isinstance(value,datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("timezone-aware Kalshi timestamp required")
    return value.astimezone(timezone.utc)


def _stamp(raw:object, *, name:str)->datetime:
    if not isinstance(raw,str) or not raw or len(raw)>64:
        raise ValueError(f"invalid Kalshi {name}")
    try:
        value=datetime.fromisoformat(raw.replace("Z","+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid Kalshi {name}") from exc
    return _utc(value)


def _ticker(raw:object, *, name:str)->str:
    if (
        not isinstance(raw,str) or not raw or len(raw)>128
        or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in raw)
    ):
        raise ValueError(f"invalid Kalshi {name}")
    return raw


def _price(raw:object, *, name:str)->str:
    if not isinstance(raw,str) or len(raw)>32:
        raise ValueError(f"Kalshi {name} must be dollar string")
    try:
        value=Decimal(raw)
    except (InvalidOperation,ValueError) as exc:
        raise ValueError(f"invalid Kalshi {name}") from exc
    if not value.is_finite() or value<0 or value>1:
        raise ValueError(f"Kalshi {name} outside 0..1")
    return str(value)


def _write_once(path:Path,obj:Mapping[str,object])->str:
    if path.exists() or path.is_symlink():
        raise ValueError("prospective Kalshi evidence path already exists")
    raw=(json.dumps(dict(obj),sort_keys=True,separators=(",",":"))+"\n").encode()
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
    if hasattr(os,"O_NOFOLLOW"):
        flags|=os.O_NOFOLLOW
    fd=os.open(path,flags,0o600)
    with os.fdopen(fd,"wb") as handle:
        os.fchmod(handle.fileno(),0o600)
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return hashlib.sha256(raw).hexdigest()


def _private_root(root:Path)->Path:
    if root.is_symlink() or not root.is_dir() or root.stat().st_mode&0o077:
        raise ValueError("Kalshi prospective root must preexist private 0700")
    return root


def _eligible_market(market:Mapping[str,object], *, planned_at:datetime)->dict[str,object]|None:
    if market.get("status")!="open" or market.get("market_type")!="binary":
        return None
    if market.get("mve_collection_ticker") not in (None,""):
        return None
    if market.get("is_provisional") is True:
        return None
    try:
        ticker=_ticker(market.get("ticker"),name="market ticker")
        event=_ticker(market.get("event_ticker"),name="event ticker")
        close=_stamp(market.get("close_time"),name="close_time")
    except ValueError:
        return None
    lead=close-planned_at
    if lead<timedelta(hours=MIN_PLAN_LEAD_HOURS):
        return None
    if lead>timedelta(days=MAX_CLOSE_AHEAD_DAYS):
        return None
    return {
        "ticker":ticker,
        "event_ticker":event,
        "close_time":close.isoformat(),
        "can_close_early":bool(market.get("can_close_early",False)),
        "reference_horizons_seconds":list(HORIZONS),
    }


def build_prospective_kalshi_plan(
    *,
    client:ProspectiveClient,
    planned_at:datetime,
    market_count:int=DEFAULT_MARKET_COUNT,
    max_pages:int=MAX_DISCOVERY_PAGES,
)->dict[str,object]:
    planned=_utc(planned_at)
    if type(market_count) is not int or not MIN_MARKET_COUNT<=market_count<=MAX_MARKET_COUNT:
        raise ValueError("Kalshi prospective plan requires 20-50 markets")
    if type(max_pages) is not int or not 1<=max_pages<=MAX_DISCOVERY_PAGES:
        raise ValueError("bounded Kalshi discovery page count required")

    candidates=[]
    seen=set()
    cursor=None
    pages=0
    for _ in range(max_pages):
        page=client.live_public_markets(status="open",limit=1000,cursor=cursor)
        pages+=1
        markets=page.get("markets") if isinstance(page,Mapping) else None
        if not isinstance(markets,list):
            raise ValueError("Kalshi public market discovery lacks markets")
        for raw in markets:
            if not isinstance(raw,Mapping):
                raise ValueError("malformed Kalshi public market")
            item=_eligible_market(raw,planned_at=planned)
            if item is None:
                continue
            ticker=item["ticker"]
            if ticker in seen:
                raise ValueError("duplicate Kalshi market across discovery pages")
            seen.add(ticker)
            candidates.append(item)
        next_cursor=page.get("cursor")
        if next_cursor in (None,""):
            break
        if not isinstance(next_cursor,str) or not next_cursor or len(next_cursor)>4096:
            raise ValueError("invalid Kalshi discovery cursor")
        cursor=next_cursor
    else:
        if cursor not in (None,""):
            raise ValueError("Kalshi public discovery exceeded bounded pages")

    ordered=sorted(
        candidates,
        key=lambda x:(_stamp(x["close_time"],name="planned close"),
                      str(x["event_ticker"]),str(x["ticker"])),
    )
    distinct=[]
    used_events=set()
    selected_tickers=set()
    for item in ordered:
        event=item["event_ticker"]
        if event in used_events:
            continue
        distinct.append(item)
        used_events.add(event)
        selected_tickers.add(item["ticker"])
        if len(distinct)>=MIN_DISTINCT_EVENTS:
            break
    if len(distinct)<MIN_DISTINCT_EVENTS:
        raise ValueError("Kalshi discovery lacks ten distinct future events")

    selected=list(distinct)
    for item in ordered:
        if len(selected)>=market_count:
            break
        if item["ticker"] in selected_tickers:
            continue
        selected.append(item)
        selected_tickers.add(item["ticker"])
    if len(selected)<market_count:
        raise ValueError("Kalshi discovery lacks requested prospective market count")
    selected=sorted(
        selected,
        key=lambda x:(_stamp(x["close_time"],name="selected close"),
                      str(x["event_ticker"]),str(x["ticker"])),
    )

    payload={
        "kind":PLAN_KIND,
        "policy_version":PLAN_POLICY,
        "hypothesis_policy_version":HYPOTHESIS_POLICY,
        "planned_at_utc":planned.isoformat(),
        "planned_market_count":len(selected),
        "minimum_distinct_events":MIN_DISTINCT_EVENTS,
        "selection_rule":
            "EARLIEST_CLOSE_THEN_EVENT_THEN_TICKER_STRUCTURAL_FIELDS_ONLY",
        "selection_uses_price":False,
        "selection_uses_outcome_direction":False,
        "selection_uses_historical_pnl":False,
        "markets":selected,
        "discovery_pages":pages,
        "network_methods":["GET"],
        "credentials_accessed":"NONE",
        "authenticated_portfolio_access":"DISABLED",
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
    raw=json.dumps(payload,sort_keys=True,separators=(",",":")).encode()
    return {**payload,"plan_sha256":hashlib.sha256(raw).hexdigest()}


def validate_prospective_kalshi_plan(plan:Mapping[str,object])->tuple[dict[str,object],...]:
    if (
        not isinstance(plan,Mapping)
        or plan.get("kind")!=PLAN_KIND
        or plan.get("policy_version")!=PLAN_POLICY
        or plan.get("hypothesis_policy_version")!=HYPOTHESIS_POLICY
        or plan.get("selection_uses_price") is not False
        or plan.get("selection_uses_outcome_direction") is not False
        or plan.get("selection_uses_historical_pnl") is not False
        or plan.get("network_methods")!=["GET"]
        or plan.get("credentials_accessed")!="NONE"
        or plan.get("demo_order_submission")!="DISABLED"
        or plan.get("live_order_submission")!="DISABLED"
    ):
        raise ValueError("invalid Kalshi prospective plan contract")
    plan_sha=plan.get("plan_sha256")
    if not isinstance(plan_sha,str) or len(plan_sha)!=64:
        raise ValueError("Kalshi prospective plan SHA missing")
    unhashed=dict(plan)
    unhashed.pop("plan_sha256",None)
    expected=hashlib.sha256(
        json.dumps(unhashed,sort_keys=True,separators=(",",":")).encode()
    ).hexdigest()
    if plan_sha!=expected:
        raise ValueError("Kalshi prospective plan SHA mismatch")
    planned=_stamp(plan.get("planned_at_utc"),name="planned_at")
    markets=plan.get("markets")
    if not isinstance(markets,list) or plan.get("planned_market_count")!=len(markets):
        raise ValueError("Kalshi planned market count mismatch")
    if len(markets)<MIN_MARKET_COUNT:
        raise ValueError("Kalshi prospective plan is too small")
    tickers=set()
    events=set()
    validated=[]
    for raw in markets:
        if not isinstance(raw,Mapping):
            raise ValueError("malformed planned Kalshi market")
        ticker=_ticker(raw.get("ticker"),name="planned ticker")
        event=_ticker(raw.get("event_ticker"),name="planned event")
        close=_stamp(raw.get("close_time"),name="planned close")
        if ticker in tickers:
            raise ValueError("duplicate planned Kalshi ticker")
        if close-planned<timedelta(hours=MIN_PLAN_LEAD_HOURS):
            raise ValueError("Kalshi plan was not frozen before fixed horizons")
        if raw.get("reference_horizons_seconds")!=list(HORIZONS):
            raise ValueError("Kalshi planned reference horizons changed")
        tickers.add(ticker)
        events.add(event)
        validated.append(dict(raw))
    if len(events)<MIN_DISTINCT_EVENTS:
        raise ValueError("Kalshi plan lacks distinct-event requirement")
    return tuple(validated)


def archive_prospective_kalshi_plan(
    plan:Mapping[str,object],
    *,
    output_root:str|Path,
)->Path:
    validate_prospective_kalshi_plan(plan)
    root=_private_root(Path(output_root))
    path=root/f"kalshi-prospective-plan-{str(plan['plan_sha256'])[:16]}.json"
    if path.exists() or path.is_symlink():
        raw=(json.dumps(dict(plan),sort_keys=True,separators=(",",":"))+"\n").encode()
        if (
            path.is_symlink() or not path.is_file() or path.stat().st_mode&0o077
            or path.read_bytes()!=raw
        ):
            raise ValueError("immutable Kalshi prospective plan collision")
        return path
    _write_once(path,plan)
    return path


def _snapshot_path(root:Path,ticker:str,horizon:int)->Path:
    return root/f"kalshi-forward-{ticker}-{horizon}s.json"


def collect_due_kalshi_snapshots(
    *,
    plan:Mapping[str,object],
    now:datetime,
    output_root:str|Path,
    client:ProspectiveClient,
)->dict[str,object]:
    markets=validate_prospective_kalshi_plan(plan)
    moment=_utc(now)
    root=_private_root(Path(output_root))
    captured=[]
    missed=[]
    not_due=0
    for item in markets:
        ticker=str(item["ticker"])
        event=str(item["event_ticker"])
        close=_stamp(item["close_time"],name="planned close")
        for horizon in HORIZONS:
            target=close-timedelta(seconds=horizon)
            path=_snapshot_path(root,ticker,horizon)
            if path.exists():
                continue
            if moment<target:
                not_due+=1
                continue
            if moment>=target+CAPTURE_WINDOW:
                missed.append({
                    "ticker":ticker,
                    "horizon_seconds":horizon,
                    "reason":"MISSED_PROSPECTIVE_CAPTURE_WINDOW_NO_BACKFILL",
                })
                continue
            response=client.live_public_market(ticker)
            market=response.get("market") if isinstance(response,Mapping) else None
            if not isinstance(market,Mapping):
                raise ValueError("Kalshi public single-market response lacks market")
            if market.get("ticker")!=ticker or market.get("event_ticker")!=event:
                raise ValueError("Kalshi public snapshot identity mismatch")
            provider_close=_stamp(market.get("close_time"),name="provider close")
            valid=(
                market.get("status")=="open"
                and provider_close==close
            )
            receipt={
                "kind":SNAPSHOT_KIND,
                "schema_version":1,
                "policy_version":PLAN_POLICY,
                "hypothesis_policy_version":HYPOTHESIS_POLICY,
                "plan_sha256":plan["plan_sha256"],
                "ticker":ticker,
                "event_ticker":event,
                "horizon_seconds_before_planned_close":horizon,
                "target_capture_utc":target.isoformat(),
                "captured_at_utc":moment.isoformat(),
                "planned_close_time_utc":close.isoformat(),
                "provider_close_time_utc":provider_close.isoformat(),
                "decision_valid":valid,
                "invalid_reason":(
                    None if valid else
                    "MARKET_NOT_OPEN_OR_CLOSE_TIME_CHANGED_BEFORE_FIXED_HORIZON"
                ),
                "yes_bid_dollars":(
                    _price(market.get("yes_bid_dollars"),name="YES bid")
                    if valid else None
                ),
                "yes_ask_dollars":(
                    _price(market.get("yes_ask_dollars"),name="YES ask")
                    if valid else None
                ),
                "last_price_dollars":(
                    _price(market.get("last_price_dollars"),name="last price")
                    if valid else None
                ),
                "outcome_direction_recorded":False,
                "result_field_recorded":False,
                "historical_backfill":False,
                "network_methods":["GET"],
                "credentials_accessed":"NONE",
                "authenticated_portfolio_access":"DISABLED",
                "demo_order_submission":"DISABLED",
                "live_order_submission":"DISABLED",
                "live_trading":"UNAVAILABLE",
            }
            _write_once(path,receipt)
            captured.append({
                "ticker":ticker,
                "horizon_seconds":horizon,
                "decision_valid":valid,
                "file":path.name,
            })
    return {
        "kind":"KALSHI_PROSPECTIVE_GET_ONLY_COLLECTION_TICK",
        "plan_sha256":plan["plan_sha256"],
        "captured":captured,
        "captured_count":len(captured),
        "missed":missed,
        "missed_count":len(missed),
        "not_due_count":not_due,
        "outcome_direction_used_for_market_selection":False,
        "historical_backfill_count":0,
        "post_settlement_decision_count":0,
        "network_methods":["GET"],
        "credentials_accessed":"NONE",
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


def main(argv:list[str]|None=None)->int:
    import argparse
    parser=argparse.ArgumentParser(
        description="Public GET-only precommitted Kalshi prospective collector"
    )
    parser.add_argument("--plan-output",type=Path)
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--collect-plan",type=Path)
    args=parser.parse_args(argv)
    client=KalshiPublicResearchClient()
    try:
        if args.plan_output is not None:
            if args.collect_plan is not None:
                raise ValueError("choose planning or capture, not both")
            plan=build_prospective_kalshi_plan(
                client=client,planned_at=datetime.now(timezone.utc)
            )
            archive_prospective_kalshi_plan(plan,output_root=args.root)
            _write_once(args.plan_output,plan)
            result=plan
        elif args.collect_plan is not None:
            raw=json.loads(args.collect_plan.read_text())
            if not isinstance(raw,dict):
                raise ValueError("Kalshi prospective plan file must contain object")
            result=collect_due_kalshi_snapshots(
                plan=raw,now=datetime.now(timezone.utc),
                output_root=args.root,client=client,
            )
        else:
            raise ValueError("planning or collection mode required")
        print(json.dumps(result,sort_keys=True,indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "status":"FAIL_CLOSED",
            "failure_class":type(exc).__name__,
            "network_methods":["GET"],
            "credentials_accessed":"NONE",
            "demo_order_submission":"DISABLED",
            "live_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        },sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())

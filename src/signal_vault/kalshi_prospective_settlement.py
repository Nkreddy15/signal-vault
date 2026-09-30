"""Separate public GET-only settlement capture for prospective Kalshi markets.

Fixed-horizon quote snapshots are created before outcome is known by Phase 81.
This module is a later stage: only after a market is publicly settled may its
binary result enter a separate immutable settlement receipt.

No settlement result is ever written back into an earlier decision snapshot.
No credentials, portfolio endpoints, demo orders, or live orders are used.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Protocol

from .kalshi_prospective_collector import (
    PLAN_POLICY,
    validate_prospective_kalshi_plan,
)

SETTLEMENT_KIND="KALSHI_PROSPECTIVE_PUBLIC_SETTLEMENT_RECEIPT_NO_ORDERS"


class SettlementClient(Protocol):
    def live_public_market(self,ticker:str)->dict[str,object]: ...


def _utc(value:datetime)->datetime:
    if (
        not isinstance(value,datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("timezone-aware Kalshi settlement timestamp required")
    return value.astimezone(timezone.utc)


def _stamp(raw:object, *, name:str)->datetime:
    if not isinstance(raw,str) or not raw or len(raw)>64:
        raise ValueError(f"invalid Kalshi {name}")
    try:
        value=datetime.fromisoformat(raw.replace("Z","+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid Kalshi {name}") from exc
    return _utc(value)


def _private_root(root:Path)->Path:
    if root.is_symlink() or not root.is_dir() or root.stat().st_mode&0o077:
        raise ValueError("Kalshi prospective root must preexist private 0700")
    return root


def _write_once(path:Path,obj:Mapping[str,object])->str:
    if path.exists() or path.is_symlink():
        raise ValueError("Kalshi settlement evidence path already exists")
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


def _settlement_path(root:Path,ticker:str)->Path:
    return root/f"kalshi-settlement-{ticker}.json"


def collect_due_kalshi_settlements(
    *,
    plan:Mapping[str,object],
    now:datetime,
    output_root:str|Path,
    client:SettlementClient,
)->dict[str,object]:
    markets=validate_prospective_kalshi_plan(plan)
    moment=_utc(now)
    root=_private_root(Path(output_root))
    captured=[]
    pending=[]
    already=0
    requests=0

    for item in markets:
        ticker=str(item["ticker"])
        event=str(item["event_ticker"])
        planned_close=_stamp(item["close_time"],name="planned close")
        path=_settlement_path(root,ticker)
        if path.exists():
            if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o077:
                raise ValueError("unsafe existing Kalshi settlement receipt")
            already+=1
            continue
        if moment<planned_close:
            pending.append({
                "ticker":ticker,
                "reason":"PLANNED_CLOSE_NOT_REACHED",
            })
            continue

        response=client.live_public_market(ticker)
        requests+=1
        market=response.get("market") if isinstance(response,Mapping) else None
        if not isinstance(market,Mapping):
            raise ValueError("Kalshi settlement lookup lacks market object")
        if market.get("ticker")!=ticker or market.get("event_ticker")!=event:
            raise ValueError("Kalshi settlement identity mismatch")

        status=market.get("status")
        if status!="settled":
            pending.append({
                "ticker":ticker,
                "reason":"PUBLIC_MARKET_NOT_SETTLED",
                "observed_status":str(status),
            })
            continue

        result=market.get("result")
        if result not in {"yes","no"}:
            raise ValueError("settled Kalshi market lacks binary result")
        settlement=_stamp(market.get("settlement_ts"),name="settlement_ts")
        if settlement>moment:
            raise ValueError("Kalshi settlement timestamp is in the future")

        receipt={
            "kind":SETTLEMENT_KIND,
            "schema_version":1,
            "policy_version":PLAN_POLICY,
            "plan_sha256":plan["plan_sha256"],
            "ticker":ticker,
            "event_ticker":event,
            "planned_close_time_utc":planned_close.isoformat(),
            "public_status":"settled",
            "resolved_result":result,
            "settlement_ts":settlement.isoformat(),
            "captured_at_utc":moment.isoformat(),
            "outcome_available_only_after_decision_stage":True,
            "earlier_decision_snapshot_rewritten":False,
            "post_settlement_decision_created":False,
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
            "resolved_result":result,
            "file":path.name,
        })

    return {
        "kind":"KALSHI_PROSPECTIVE_SETTLEMENT_COLLECTION_TICK",
        "plan_sha256":plan["plan_sha256"],
        "settlements_captured":captured,
        "captured_count":len(captured),
        "pending":pending,
        "pending_count":len(pending),
        "already_captured_count":already,
        "network_request_count":requests,
        "network_methods":["GET"],
        "credentials_accessed":"NONE",
        "post_settlement_decision_count":0,
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


def main(argv:list[str]|None=None)->int:
    import argparse
    from .kalshi_public_research import KalshiPublicResearchClient

    parser=argparse.ArgumentParser(
        description="Public GET-only settlement capture for precommitted Kalshi markets"
    )
    parser.add_argument("--plan",type=Path,required=True)
    parser.add_argument("--root",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        raw=json.loads(args.plan.read_text())
        if not isinstance(raw,dict):
            raise ValueError("Kalshi prospective plan file must contain object")
        result=collect_due_kalshi_settlements(
            plan=raw,
            now=datetime.now(timezone.utc),
            output_root=args.root,
            client=KalshiPublicResearchClient(),
        )
        print(json.dumps(result,sort_keys=True,indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "status":"FAIL_CLOSED",
            "failure_class":type(exc).__name__,
            "network_methods":["GET"],
            "credentials_accessed":"NONE",
            "post_settlement_decision_count":0,
            "demo_order_submission":"DISABLED",
            "live_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        },sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())

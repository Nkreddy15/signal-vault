"""Manual long-horizon US-equity historical GET orchestration.

Splits up to ~400 calendar days into the existing independently verified XNYS
chunks, then invokes the already bounded IEX historical collector once per
chunk. Each chunk gets a new private folder; prior evidence is never overwritten.

This module is manual GitHub-Actions-only, GET-only, and has no order pathway.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from .ci_historical_equities import execute_manual_equity_history
from .historical_equity_chunks import long_horizon_equity_plan

APPROVAL="LONG_HORIZON_XNYS_IEX_HISTORICAL_DATA_GET_ONLY"
ROOT=Path("private-equity-long-artifacts")


def _date(raw:object)->date:
    if not isinstance(raw,str):
        raise ValueError("ISO date required")
    return date.fromisoformat(raw)


def resolve_long_equity_plan(*,env:Mapping[str,str],as_of:datetime)->dict[str,object]:
    if (
        env.get("GITHUB_ACTIONS")!="true"
        or env.get("GITHUB_EVENT_NAME")!="workflow_dispatch"
        or env.get("GITHUB_REPOSITORY")!="Nkreddy15/signal-vault"
        or env.get("GITHUB_REF")!="refs/heads/main"
        or env.get("SIGNAL_VAULT_LONG_EQUITY_READ_APPROVED")!=APPROVAL
    ):
        raise PermissionError("explicit manual main-only long-equity approval required")
    return long_horizon_equity_plan(
        start_date=_date(env.get("SIGNAL_VAULT_LONG_EQUITY_START_DATE")),
        end_date_exclusive=_date(env.get("SIGNAL_VAULT_LONG_EQUITY_END_DATE_EXCLUSIVE")),
        as_of=as_of,
    )


def _create_root(root:Path)->None:
    if root.exists() or root.is_symlink():
        raise ValueError("long-equity output root must be new")
    root.mkdir(mode=0o700)
    if root.stat().st_mode & 0o077:
        raise PermissionError("long-equity output root must be private")


def execute_long_equity_history(
    *,
    env:Mapping[str,str],
    as_of:datetime,
    output_root:Path=ROOT,
    runner:Callable[...,dict[str,object]]=execute_manual_equity_history,
)->dict[str,object]:
    plan=resolve_long_equity_plan(env=env,as_of=as_of)
    _create_root(output_root)
    chunks=plan["chunks"]
    results=[]
    for index,chunk in enumerate(chunks,1):
        chunk_env=dict(env)
        chunk_env["SIGNAL_VAULT_EQUITY_READ_APPROVED"]="HISTORICAL_IEX_XNYS_FULL_CORE_HOURS_DATA_GET_ONLY"
        chunk_env["SIGNAL_VAULT_EQUITY_START_DATE"]=chunk["start_date"]
        chunk_env["SIGNAL_VAULT_EQUITY_END_DATE_EXCLUSIVE"]=chunk["end_date_exclusive"]
        chunk_env["SIGNAL_VAULT_EQUITY_SYMBOLS"]="AAPL AMD MSFT NVDA QQQ SPY"
        chunk_env["SIGNAL_VAULT_EQUITY_FEED"]="iex"
        folder=output_root/f"chunk-{index:03d}"
        result=runner(
            env=chunk_env,
            as_of=as_of,
            output_folder=folder,
        )
        if result.get("broker_order_submission")!="DISABLED":
            raise ValueError("historical chunk unexpectedly exposed order submission")
        results.append({
            "chunk_index":index,
            "start_date":chunk["start_date"],
            "end_date_exclusive":chunk["end_date_exclusive"],
            "completed_exchange_sessions":result["completed_exchange_sessions"],
            "historical_bars_per_asset":result["historical_bars_per_asset"],
            "report_sha256":result["report_sha256"],
        })
    manifest={
        "kind":"MANUAL_LONG_HORIZON_XNYS_IEX_RESEARCH_MANIFEST",
        "symbols":["AAPL","AMD","MSFT","NVDA","QQQ","SPY"],
        "feed":"iex",
        "chunk_count":len(results),
        "chunks":results,
        "prospective_observations_verified":0,
        "credentials_in_manifest":False,
        "broker_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
    raw=(json.dumps(manifest,sort_keys=True,indent=2)+"\n").encode()
    path=output_root/"long_horizon_manifest.json"
    with path.open("xb") as fh:
        os.fchmod(fh.fileno(),0o600)
        fh.write(raw)
        fh.flush()
        os.fsync(fh.fileno())
    return {
        **manifest,
        "manifest_sha256":hashlib.sha256(raw).hexdigest(),
    }


def main(argv:list[str]|None=None)->int:
    import argparse
    parser=argparse.ArgumentParser(
        description="MANUAL long-horizon XNYS IEX historical GET-only orchestrator"
    )
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run",action="store_true")
    group.add_argument("--download-history",action="store_true")
    args=parser.parse_args(argv)
    now=datetime.now(timezone.utc)
    try:
        result=(
            resolve_long_equity_plan(env=os.environ,as_of=now)
            if args.dry_run
            else execute_long_equity_history(env=os.environ,as_of=now)
        )
        print(json.dumps(result,sort_keys=True,indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "kind":"MANUAL_LONG_HORIZON_XNYS_IEX_RESEARCH",
            "status":"FAIL_CLOSED",
            "failure_class":type(exc).__name__,
            "credential_values_in_output":False,
            "broker_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        },sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())

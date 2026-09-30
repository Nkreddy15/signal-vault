"""Existing-volume all-market GET-only Railway research cron.

Runs the existing BTC/crypto/stocks research cron first. Only after original
BTC evidence integrity remains proven does it run the optional public Kalshi
prospective sidecar. The same persistent volume is reused with three explicit
research child namespaces; every other BTC byte remains covered by the mutation
fingerprint.

No new Railway service/volume, no paid resource, no broker POST, no demo order,
and no live-money execution are introduced.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from .btc_evidence_fingerprint import fingerprint_btc_evidence_tree
from .cloud_forward_service import CLOUD_ROOT
from .kalshi_cloud_sidecar import (
    CHILD as KALSHI_CHILD,
    ROOT_ENV as KALSHI_ROOT_ENV,
    run_kalshi_sidecar_once,
)
from .railway_btc_first_dual_cron import (
    BTC_FINGERPRINT_EXCLUDED_CHILDREN,
    BTC_HEALTHY,
    BTC_MINIMUM_FREE_RESERVE_BYTES,
)
from .railway_multimarket_research_cron import combined_multimarket_once
from .all_market_forward_status import all_market_forward_status

KALSHI_TOTAL_EVIDENCE_CAP_BYTES=8*1024*1024
KALSHI_MAX_NEW_TICK_BUDGET_BYTES=1*1024*1024


def _kalshi_storage_budget(*,btc_root:Path)->dict[str,int]:
    if btc_root.is_symlink() or not btc_root.is_dir():
        raise ValueError("original BTC volume root unavailable")
    stats=os.statvfs(btc_root)
    available=stats.f_bavail*stats.f_frsize
    if available<(
        BTC_MINIMUM_FREE_RESERVE_BYTES+KALSHI_MAX_NEW_TICK_BUDGET_BYTES
    ):
        raise ValueError("Kalshi sidecar would consume protected BTC reserve")
    root=btc_root/KALSHI_CHILD
    total=0
    inspected=0
    if root.exists():
        if root.is_symlink() or not root.is_dir():
            raise ValueError("Kalshi research child must be real directory")
        for item in root.rglob("*"):
            inspected+=1
            if inspected>10_000 or item.is_symlink():
                raise ValueError("unsafe or excessive Kalshi evidence tree")
            if item.is_file():
                total+=item.stat().st_size
                if (
                    total+KALSHI_MAX_NEW_TICK_BUDGET_BYTES
                    >KALSHI_TOTAL_EVIDENCE_CAP_BYTES
                ):
                    raise ValueError("Kalshi evidence cap reached; preserve BTC volume")
            elif not item.is_dir():
                raise ValueError("unexpected Kalshi evidence inode")
    return {
        "available_bytes_before_kalshi":available,
        "existing_kalshi_evidence_bytes":total,
    }


def combined_all_markets_once(
    *,
    now:datetime,
    environ:Mapping[str,str]|None=None,
    btc_root:Path=CLOUD_ROOT,
    core_runner:Callable[...,dict[str,object]]=combined_multimarket_once,
    kalshi_runner:Callable[...,dict[str,object]]=run_kalshi_sidecar_once,
    kalshi_client_factory:Callable[[],object]|None=None,
)->dict[str,object]:
    env=os.environ if environ is None else environ
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("timezone-aware all-market cron timestamp required")
    stamp=now.astimezone(timezone.utc)
    output={
        "kind":"RAILWAY_EXISTING_VOLUME_ALL_MARKETS_GET_ONLY_CRON",
        "core_status":"NOT_RUN",
        "kalshi_status":"NOT_RUN",
        "new_Railway_service_created":False,
        "new_Railway_volume_created":False,
        "new_paid_resource_created":False,
        "broker_order_submission":"DISABLED",
        "paper_order_submission":"DISABLED",
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "automatic_live_trading":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }

    core=core_runner(
        now=stamp,
        environ=env,
        btc_root=btc_root,
    )
    if not isinstance(core,dict) or not isinstance(
        core.get("crypto_btc_status"),str
    ):
        raise ValueError("core BTC/crypto/stock cron returned malformed result")
    output["core"]=core
    output["core_status"]=core["crypto_btc_status"]
    output["equity_status"]=core.get("equity_status")

    if core["crypto_btc_status"] not in BTC_HEALTHY:
        output["kalshi_status"]="SKIPPED_BTC_NOT_HEALTHY"
        return output
    if core.get("btc_evidence_changed_during_equity_stage") is not False:
        output["kalshi_status"]="SKIPPED_BTC_INTEGRITY_NOT_PROVEN"
        return output

    before=None
    try:
        before=fingerprint_btc_evidence_tree(
            btc_root,
            excluded_sidecar_names=BTC_FINGERPRINT_EXCLUDED_CHILDREN,
        )
        output["btc_evidence_before_kalshi_SHA256"]=before["tree_sha256"]
        output.update(_kalshi_storage_budget(btc_root=btc_root))

        kalshi_env=dict(env)
        kalshi_env.setdefault(KALSHI_ROOT_ENV,str(btc_root))
        kwargs={"env":kalshi_env,"now":stamp}
        if kalshi_client_factory is not None:
            kwargs["client_factory"]=kalshi_client_factory
        kalshi=kalshi_runner(**kwargs)
        if not isinstance(kalshi,dict) or not isinstance(kalshi.get("status"),str):
            raise ValueError("Kalshi sidecar returned malformed result")
        output["kalshi"]=kalshi
        output["kalshi_status"]=kalshi["status"]
    except Exception as exc:
        output["kalshi_status"]="FAILED_SAFE_OR_BLOCKED_KALSHI_SIDECAR_ONLY"
        output["kalshi_failure_class"]=type(exc).__name__

    if before is not None:
        try:
            after=fingerprint_btc_evidence_tree(
                btc_root,
                excluded_sidecar_names=BTC_FINGERPRINT_EXCLUDED_CHILDREN,
            )
            output["btc_evidence_after_kalshi_SHA256"]=after["tree_sha256"]
            changed=after["tree_sha256"]!=before["tree_sha256"]
            output["btc_evidence_changed_during_kalshi_stage"]=changed
            if changed:
                output["kalshi_status"]="FAILED_BTC_EVIDENCE_MUTATION_GUARD"
                output["kalshi_failure_class"]="BtcEvidenceFingerprintMismatch"
                output["original_BTC_status_preserved"]=False
                output["existing_BTC_evidence_deleted_or_reset"]=None
            else:
                output["original_BTC_status_preserved"]=True
                output["existing_BTC_evidence_deleted_or_reset"]=False
        except Exception as exc:
            output["btc_evidence_changed_during_kalshi_stage"]=None
            output["btc_evidence_integrity_recheck_failure_class"]=type(exc).__name__
            output["original_BTC_status_preserved"]=None
            output["existing_BTC_evidence_deleted_or_reset"]=None
    else:
        output["btc_evidence_changed_during_kalshi_stage"]=None
        output["original_BTC_status_preserved"]=None
        output["existing_BTC_evidence_deleted_or_reset"]=None

    if output.get("original_BTC_status_preserved") is True:
        try:
            readiness=all_market_forward_status(
                environ=env,
                root=btc_root,
            )
            output["post_tick_readiness_status"]="AVAILABLE"
            output["post_tick_readiness"]=readiness
        except Exception as exc:
            output["post_tick_readiness_status"]="FAILED_SAFE"
            output["post_tick_readiness_failure_class"]=type(exc).__name__
    else:
        output["post_tick_readiness_status"]="SKIPPED_BTC_INTEGRITY_NOT_PROVEN"
    return output


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(
        description="Existing-volume BTC crypto stocks Kalshi GET-only research cron"
    )
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--once",action="store_true")
    modes.add_argument("--status",action="store_true")
    parsed=parser.parse_args(argv)
    if parsed.status:
        result=all_market_forward_status()
        code=0
    else:
        result=combined_all_markets_once(now=datetime.now(timezone.utc))
        code=0 if result["core_status"] in BTC_HEALTHY else 2
    print(json.dumps(result,sort_keys=True,indent=2))
    return code


if __name__=="__main__":
    raise SystemExit(main())

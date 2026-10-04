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
    BASENAME as SIX_CRYPTO_BASENAME,
    BTC_FINGERPRINT_EXCLUDED_CHILDREN,
    BTC_HEALTHY,
    BTC_MINIMUM_FREE_RESERVE_BYTES,
)
from .railway_multimarket_research_cron import combined_multimarket_once
from .all_market_forward_status import all_market_forward_status
from .all_market_dashboard import build_dashboard_snapshot
from .dashboard_snapshot_archive import archive_dashboard_snapshot
from .six_crypto_shadow import inspect_six_crypto_shadow
from .current_compact_crypto_snapshot import current_compact_crypto_snapshot
from .current_compact_stock_snapshot import current_compact_stock_snapshot
from .equity_cloud_sidecar import (
    CHILD as EQUITY_CHILD,
    KEY_ENV as EQUITY_KEY_ENV,
    SECRET_ENV as EQUITY_SECRET_ENV,
)
from .equity_forward_archive_audit import load_current_equity_forward_segment
from .equity_model_warmup import collect_stock_model_warmup
from .current_portfolio_brain import build_current_portfolio_brain

KALSHI_TOTAL_EVIDENCE_CAP_BYTES=8*1024*1024
KALSHI_MAX_NEW_TICK_BUDGET_BYTES=1*1024*1024

_KALSHI_DASHBOARD_FIELDS=(
    "status",
    "planning_failure_code",
    "public_get_requests_used",
    "public_get_budget",
    "planned_market_count",
    "planned_buffer_markets",
    "prospective_snapshots_captured",
    "prospective_snapshots_missed",
    "settlement_receipts_captured",
    "settlements_pending",
)


def _kalshi_tick_for_dashboard(output:Mapping[str,object])->dict[str,object]:
    raw=output.get("kalshi")
    if isinstance(raw,Mapping):
        item={key:raw.get(key) for key in _KALSHI_DASHBOARD_FIELDS if key in raw}
        item["status"]=raw.get("status","UNKNOWN")
        return item
    return {
        "status":output.get("kalshi_status","UNKNOWN"),
        "failure_class":output.get("kalshi_failure_class"),
    }


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

    try:
        stock_root=btc_root/EQUITY_CHILD
        if stock_root.exists():
            _,_,stock_grid=load_current_equity_forward_segment(stock_root)
            warmup=collect_stock_model_warmup(
                stock_root=stock_root,
                first_forward_open=stock_grid[0],
                as_of=stamp,
                key=str(env.get(EQUITY_KEY_ENV,"")),
                secret=str(env.get(EQUITY_SECRET_ENV,"")),
            )
            output["stock_model_warmup_status"]=warmup.get("status")
            output["stock_model_warmup_core_hours"]=warmup.get(
                "warmup_core_hours_per_asset"
            )
            output["stock_model_warmup_network_requests"]=warmup.get(
                "network_requests",0
            )
            output["stock_model_warmup_counts_as_prospective"]=False
        else:
            output["stock_model_warmup_status"]="NOT_STARTED"
    except Exception as exc:
        output["stock_model_warmup_status"]="FAILED_SAFE"
        output["stock_model_warmup_failure_class"]=type(exc).__name__

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
            try:
                dashboard=build_dashboard_snapshot(
                    root=btc_root,
                    environ=env,
                )
                dashboard["latest_kalshi_tick"]=_kalshi_tick_for_dashboard(output)
                dashboard_path=archive_dashboard_snapshot(
                    dashboard,
                    base=btc_root,
                )
                output["dashboard_snapshot_status"]="AVAILABLE"
                output["dashboard_snapshot_file"]=dashboard_path.name
                output["dashboard_snapshot_order_submission"]="DISABLED"
                research=dashboard.get("strategy_research",{})
                if isinstance(research,Mapping):
                    output["dashboard_strategy_research_status"]=research.get("status")
                    output["dashboard_strategy_research_family"]=research.get("candidate_family")
                    output["dashboard_strategy_research_selected_strategy"]=research.get("selected_strategy")
                    output["dashboard_strategy_research_paper_activation_permitted"]=(
                        research.get("paper_activation_permitted") is True
                    )
                try:
                    shadow=inspect_six_crypto_shadow(
                        root=btc_root/SIX_CRYPTO_BASENAME,
                    )
                    if shadow.get("kind")=="OFFLINE_SIX_CRYPTO_SHA_CHAINED_SHADOW_ONLY":
                        decisions=shadow.get("predeclared_flat_and_held_hypothetical_decisions",{})
                        btc=decisions.get("BTC/USD",{}) if isinstance(decisions,Mapping) else {}
                        if isinstance(btc,Mapping):
                            actions={}
                            for name,item in btc.items():
                                flat=item.get("flat") if isinstance(item,Mapping) else None
                                action=flat.get("hypothetical_action") if isinstance(flat,Mapping) else None
                                if isinstance(name,str) and action in ("buy","hold","sell"):
                                    actions[name]=action
                            output["current_btc_shadow_status"]="AVAILABLE"
                            output["current_btc_shadow_close_utc"]=shadow.get("latest_newly_observed_UTC_close")
                            output["current_btc_flat_actions"]=actions
                            output["current_btc_shadow_payload_sha256"]=shadow.get("shadow_payload_sha256")
                            output["current_btc_actions_are_order_authority"]=False
                        else:
                            output["current_btc_shadow_status"]="FAILED_SAFE"
                    else:
                        output["current_btc_shadow_status"]="NO_GENUINE_PROSPECTIVE_SHADOW"
                except Exception as exc:
                    output["current_btc_shadow_status"]="FAILED_SAFE"
                    output["current_btc_shadow_failure_class"]=type(exc).__name__
                try:
                    compact=current_compact_crypto_snapshot(
                        root=btc_root/SIX_CRYPTO_BASENAME,
                    )
                    output["current_compact_crypto_model_status"]=compact.get("status")
                    output["current_compact_crypto_model_snapshot"]=compact
                    output["current_compact_crypto_model_order_submission"]="DISABLED"
                except Exception as exc:
                    output["current_compact_crypto_model_status"]="FAILED_SAFE"
                    output["current_compact_crypto_model_failure_class"]=type(exc).__name__
                try:
                    stock_root=btc_root/EQUITY_CHILD
                    if not stock_root.exists():
                        output["current_compact_stock_model_status"]="NOT_STARTED"
                    else:
                        stock_compact=current_compact_stock_snapshot(
                            root=stock_root,
                        )
                        output["current_compact_stock_model_status"]=stock_compact.get("status")
                        output["current_compact_stock_model_snapshot"]=stock_compact
                    output["current_compact_stock_model_order_submission"]="DISABLED"
                except Exception as exc:
                    output["current_compact_stock_model_status"]="FAILED_SAFE"
                    output["current_compact_stock_model_failure_class"]=type(exc).__name__
                try:
                    brain=build_current_portfolio_brain(
                        root=btc_root,
                        as_of=stamp,
                    )
                    output["current_portfolio_brain_status"]="AVAILABLE"
                    output["current_portfolio_brain"]=brain
                    output["current_portfolio_brain_order_submission"]="DISABLED"
                except Exception as exc:
                    output["current_portfolio_brain_status"]="FAILED_SAFE"
                    output["current_portfolio_brain_failure_class"]=type(exc).__name__
            except Exception as exc:
                output["dashboard_snapshot_status"]="FAILED_SAFE"
                output["dashboard_snapshot_failure_class"]=type(exc).__name__
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

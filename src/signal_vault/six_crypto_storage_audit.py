"""Offline sidecar storage/retention audit; never prunes evidence.

The deployed BTC-first dual collector shares one 500MB persistent volume.
The six-crypto namespace is hard-capped and may never delete original BTC
evidence to make room. This module explains actual byte use and whether
current observed receipt/shadow sizes suggest the current segment can reach
the 168-source-hour and 169-source-hour/168-scored milestones before either
the sidecar hard cap or reserved BTC free-space floor is reached.

This is a descriptive capacity projection, NOT an automatic retention policy,
not a request to buy storage, and not permission to delete any source.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
from datetime import datetime
from pathlib import Path

from .crypto_universe_forward import (
    SHARED_VOLUME_SIDECAR_ROOT, _audit_chain, _safe_root, _utc,
)
from .railway_btc_first_dual_cron import (
    BASENAME,
    BTC_MINIMUM_FREE_RESERVE_BYTES,
    MAX_NEW_SIDECAR_TICK_BUDGET_BYTES,
    SIX_MARKET_TOTAL_EVIDENCE_CAP_BYTES,
)
from .six_crypto_shadow import FOLDER

SOURCE_MILESTONE=168
SCORED_OUTCOME_SOURCE_HOURS=169


def _tree_bytes(root:Path) -> tuple[int,int]:
    total=0
    files=0
    inspected=0
    for item in root.rglob("*"):
        inspected+=1
        if inspected>30_000 or item.is_symlink():
            raise ValueError("unsafe or excessive sidecar evidence tree")
        if item.is_file():
            if item.stat().st_mode&0o077:
                raise PermissionError("sidecar evidence files must remain owner-only")
            size=item.stat().st_size
            if size<0:
                raise ValueError("invalid negative file size")
            total+=size
            files+=1
        elif not item.is_dir():
            raise ValueError("unexpected non-file evidence inode")
    return total,files


def _prospective_tick_sizes(
    root:Path,
    chain:list[dict[str,object]],
) -> list[int]:
    receipts=root/"hourly-receipts"
    shadows=root/FOLDER
    sizes=[]
    for receipt in chain:
        if receipt["event"]!="ONE_NEW_CONTIGUOUS_PROSPECTIVE_HOUR":
            continue
        close=_utc(datetime.fromisoformat(receipt["closed_hour_utc"]))
        receipt_file=receipts/("hour-"+close.strftime("%Y%m%dT%H%MZ")+".json")
        shadow_file=shadows/("shadow-hour-"+close.strftime("%Y%m%dT%H%MZ")+".json")
        if (receipt_file.is_symlink() or shadow_file.is_symlink() or
                not receipt_file.is_file() or not shadow_file.is_file()):
            raise ValueError("prospective capacity sample requires exact receipt+shadow pair")
        if receipt_file.stat().st_mode&0o077 or shadow_file.stat().st_mode&0o077:
            raise PermissionError("prospective evidence pair must be private")
        sizes.append(receipt_file.stat().st_size+shadow_file.stat().st_size)
    return sizes


def sidecar_storage_audit(
    *,
    btc_root:Path,
    sidecar_root:Path=SHARED_VOLUME_SIDECAR_ROOT,
) -> dict[str,object]:
    """Read-only byte budget + current-segment milestone projection."""
    btc_root=Path(btc_root)
    sidecar_root=Path(sidecar_root)
    if sidecar_root!=btc_root/BASENAME:
        raise ValueError("storage audit must inspect exact deployed sidecar child")
    if (btc_root.is_symlink() or not btc_root.is_dir() or
            btc_root.stat().st_mode&0o077):
        raise ValueError("BTC volume root must remain private real directory")
    if not sidecar_root.exists():
        stat=os.statvfs(btc_root)
        available=stat.f_bavail*stat.f_frsize
        return {
            "kind":"OFFLINE_SIX_CRYPTO_STORAGE_AND_RETENTION_AUDIT",
            "status":"SIDECAR_NOT_YET_CREATED",
            "sidecar_bytes":0,
            "sidecar_file_count":0,
            "filesystem_available_bytes":available,
            "btc_reserved_free_bytes":BTC_MINIMUM_FREE_RESERVE_BYTES,
            "sidecar_hard_cap_bytes":SIX_MARKET_TOTAL_EVIDENCE_CAP_BYTES,
            "automatic_pruning":"DISABLED",
            "evidence_deletion":"DISABLED",
            "network_requests":"NONE",
            "broker_order_submission":"DISABLED",
        }

    root=_safe_root(sidecar_root)
    chain=_audit_chain(root)
    total_bytes,file_count=_tree_bytes(root)
    if total_bytes>SIX_MARKET_TOTAL_EVIDENCE_CAP_BYTES:
        raise ValueError("sidecar already exceeds declared hard evidence cap")
    stat=os.statvfs(btc_root)
    available=stat.f_bavail*stat.f_frsize
    ticks=_prospective_tick_sizes(root,chain)
    active_segment=chain[-1]["segment_index"] if chain else 0
    current=[
        r for r in chain
        if r["segment_index"]==active_segment and
           r["event"]=="ONE_NEW_CONTIGUOUS_PROSPECTIVE_HOUR"
    ]
    prospective_hours=len(current)

    report={
        "kind":"OFFLINE_SIX_CRYPTO_STORAGE_AND_RETENTION_AUDIT",
        "status":"AUDITED",
        "sidecar_bytes":total_bytes,
        "sidecar_file_count":file_count,
        "sidecar_hard_cap_bytes":SIX_MARKET_TOTAL_EVIDENCE_CAP_BYTES,
        "sidecar_hard_cap_remaining_bytes":
            SIX_MARKET_TOTAL_EVIDENCE_CAP_BYTES-total_bytes,
        "filesystem_available_bytes":available,
        "btc_reserved_free_bytes":BTC_MINIMUM_FREE_RESERVE_BYTES,
        "bytes_available_above_BTC_reserve":
            max(0,available-BTC_MINIMUM_FREE_RESERVE_BYTES),
        "maximum_single_new_tick_budget_bytes":
            MAX_NEW_SIDECAR_TICK_BUDGET_BYTES,
        "current_segment_prospective_source_hours":prospective_hours,
        "source_168_hours_remaining":max(0,SOURCE_MILESTONE-prospective_hours),
        "source_169_hours_remaining_for_168_scored_outcomes":
            max(0,SCORED_OUTCOME_SOURCE_HOURS-prospective_hours),
        "observed_prospective_receipt_shadow_pair_count":len(ticks),
        "automatic_pruning":"DISABLED",
        "evidence_deletion":"DISABLED",
        "original_BTC_files_may_be_deleted_for_sidecar":"NEVER",
        "network_requests":"NONE",
        "credentials_accessed":"NONE",
        "broker_order_submission":"DISABLED",
    }
    hard_next_ok=(
        available>=BTC_MINIMUM_FREE_RESERVE_BYTES+
                   MAX_NEW_SIDECAR_TICK_BUDGET_BYTES and
        total_bytes+MAX_NEW_SIDECAR_TICK_BUDGET_BYTES<=
            SIX_MARKET_TOTAL_EVIDENCE_CAP_BYTES
    )
    report["hard_runtime_guard_allows_one_more_tick"]=hard_next_ok

    if ticks:
        largest=max(ticks)
        mean=int(statistics.fmean(ticks))
        median=int(statistics.median(ticks))
        report.update({
            "observed_tick_pair_bytes_min":min(ticks),
            "observed_tick_pair_bytes_median":median,
            "observed_tick_pair_bytes_mean":mean,
            "observed_tick_pair_bytes_max":largest,
        })
        # Conservative descriptive projection uses the LARGEST observed
        # receipt+shadow pair so far, not mean. It is not a guarantee: future
        # provider JSON or strategy payloads can grow.
        remaining_to_168=max(0,SOURCE_MILESTONE-prospective_hours)
        remaining_to_169=max(0,SCORED_OUTCOME_SOURCE_HOURS-prospective_hours)
        projected_168=total_bytes+largest*remaining_to_168
        projected_169=total_bytes+largest*remaining_to_169
        report.update({
            "projected_sidecar_bytes_at_168_source_hours_using_largest_observed_tick":
                projected_168,
            "projected_sidecar_bytes_at_169_source_hours_using_largest_observed_tick":
                projected_169,
            "projection_168_below_sidecar_cap":
                projected_168<=SIX_MARKET_TOTAL_EVIDENCE_CAP_BYTES,
            "projection_169_below_sidecar_cap":
                projected_169<=SIX_MARKET_TOTAL_EVIDENCE_CAP_BYTES,
            "projection_168_preserves_current_BTC_free_reserve_if_no_other_disk_growth":
                available-(largest*remaining_to_168)>=BTC_MINIMUM_FREE_RESERVE_BYTES,
            "projection_169_preserves_current_BTC_free_reserve_if_no_other_disk_growth":
                available-(largest*remaining_to_169)>=BTC_MINIMUM_FREE_RESERVE_BYTES,
            "projection_is_not_a_guarantee":True,
        })
    else:
        report.update({
            "projection_status":
                "WAIT_FOR_FIRST_PROSPECTIVE_RECEIPT_PLUS_SHADOW_PAIR",
            "projection_is_not_a_guarantee":True,
        })

    if not hard_next_ok:
        report["status"]="HARD_GUARD_WOULD_SKIP_NEXT_SIDECAR_TICK"
    elif ticks and (
        not report["projection_169_below_sidecar_cap"] or
        not report[
            "projection_169_preserves_current_BTC_free_reserve_if_no_other_disk_growth"]):
        report["status"]="CAPACITY_PROJECTION_WARNING_PRESERVE_ALL_EVIDENCE"
    else:
        report["status"]="CURRENT_STORAGE_GUARDS_HEALTHY"
    return report


def main(argv:list[str]|None=None) -> int:
    parser=argparse.ArgumentParser(
        description="Offline read-only sidecar storage projection; never prunes evidence.")
    parser.add_argument("--btc-root",type=Path,required=True)
    parser.add_argument("--sidecar-root",type=Path,default=SHARED_VOLUME_SIDECAR_ROOT)
    args=parser.parse_args(argv)
    try:
        result=sidecar_storage_audit(
            btc_root=args.btc_root,sidecar_root=args.sidecar_root)
        okay=result["status"] not in (
            "HARD_GUARD_WOULD_SKIP_NEXT_SIDECAR_TICK",)
    except Exception as exc:
        result={
            "kind":"OFFLINE_SIX_CRYPTO_STORAGE_AND_RETENTION_AUDIT",
            "status":"BLOCKED",
            "failure_class":type(exc).__name__,
            "automatic_pruning":"DISABLED",
            "evidence_deletion":"DISABLED",
            "network_requests":"NONE",
            "broker_order_submission":"DISABLED",
        }
        okay=False
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if okay else 2


if __name__=="__main__":
    raise SystemExit(main())

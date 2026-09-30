"""Read-only integrity/status view across deployed BTC-first and six-crypto sidecar.

This module NEVER calls a provider, reads credentials, mutates a journal,
creates a sidecar, repairs permissions, or submits an order. It only reuses
the already strict BTC and six-crypto local evidence auditors.

The two streams have intentionally different prospectivity histories:
BTC began earlier, while the six-crypto sidecar's first 72h source pull is
retrospective baseline and counts ZERO prospective hours. A healthy same-tick
deployment should therefore have equal latest closed-hour timestamps after
bootstrap, but very different prospective counts.

One six-crypto clock hour is six asset-bars but counts as exactly ONE
independent prospective UTC hour. The 168-hour readiness flag is based on
the current contiguous sidecar segment only and resets after any missed hour.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .cloud_forward_service import CLOUD_ROOT, cloud_status
from .crypto_universe_forward import (
    SHARED_VOLUME_SIDECAR_ROOT, universe_status,
)
from .railway_btc_first_dual_cron import BASENAME
from .six_crypto_shadow import inspect_six_crypto_shadow

HOUR=timedelta(hours=1)


def _utc(raw:str) -> datetime:
    value=datetime.fromisoformat(raw)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("evidence timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _btc_latest_close(btc:dict[str,object]) -> datetime|None:
    verified=btc.get("verified_collector")
    if not isinstance(verified,dict):
        return None
    start=verified.get("last_anchored_bar_started_utc")
    if not isinstance(start,str):
        return None
    return _utc(start)+HOUR


def dual_forward_integrity_status(
    *,
    btc_root:Path=CLOUD_ROOT,
    sidecar_root:Path=SHARED_VOLUME_SIDECAR_ROOT,
) -> dict[str,object]:
    """Audit both evidence trees without credentials/network/writes."""
    btc_root=Path(btc_root)
    sidecar_root=Path(sidecar_root)
    expected=btc_root/BASENAME
    if sidecar_root!=expected:
        raise ValueError("sidecar status must inspect exact isolated child namespace")
    if sidecar_root.is_symlink():
        raise ValueError("sidecar root cannot be a symlink")

    btc=cloud_status(root=btc_root)
    out:dict[str,object]={
        "kind":"OFFLINE_BTC_FIRST_SIX_CRYPTO_COMBINED_INTEGRITY_STATUS",
        "status":"BLOCKED",
        "btc":btc,
        "sidecar":{
            "status":"NOT_YET_CREATED",
            "prospective_hours":0,
            "prospective_asset_bars":0,
        },
        "network_requests":"NONE",
        "credentials_accessed":"NONE",
        "files_modified":False,
        "broker_order_submission":"DISABLED",
        "automatic_paper_trading":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
    if btc.get("status") not in ("READ_ONLY_STATUS_AVAILABLE","PAUSED"):
        out["reason_code"]="BTC_EVIDENCE_NOT_AUDITABLE"
        return out
    verified=btc.get("verified_collector")
    if not isinstance(verified,dict):
        out["reason_code"]="BTC_VERIFIED_COLLECTOR_STATUS_MISSING"
        return out

    btc_count=verified.get("prospective_observations_verified")
    if type(btc_count) is not int or btc_count<0:
        out["reason_code"]="BTC_PROSPECTIVE_COUNT_INVALID"
        return out
    out["btc_prospective_observations_verified"]=btc_count
    btc_close=_btc_latest_close(btc)
    out["btc_latest_verified_closed_hour_utc"]=(
        btc_close.isoformat() if btc_close else None)

    if not sidecar_root.exists():
        out.update(
            status=("BTC_ONLY_HEALTHY_WAITING_FOR_FIRST_SIX_CRYPTO_TICK"
                    if btc.get("status")=="READ_ONLY_STATUS_AVAILABLE"
                    else "BTC_PAUSED_NO_SIX_CRYPTO_STATUS"),
            reason_code="SIX_CRYPTO_SIDECAR_NOT_YET_CREATED")
        return out
    if not sidecar_root.is_dir() or sidecar_root.stat().st_mode&0o077:
        out["reason_code"]="SIX_CRYPTO_SIDECAR_NOT_PRIVATE_DIRECTORY"
        return out

    source=universe_status(root=sidecar_root)
    shadow=inspect_six_crypto_shadow(root=sidecar_root)
    out["sidecar"]={
        "source":source,
        "shadow":shadow,
        "prospective_hours":source[
            "current_segment_independent_prospective_hours"],
        "prospective_asset_bars":source[
            "current_segment_prospective_asset_bar_count"],
    }
    side_latest=source.get("latest_hour_utc")
    side_close=_utc(side_latest) if isinstance(side_latest,str) else None
    out["six_crypto_latest_verified_closed_hour_utc"]=(
        side_close.isoformat() if side_close else None)

    if btc_close is not None and side_close is not None:
        delta=(btc_close-side_close).total_seconds()/3600
        if delta!=int(delta):
            out["reason_code"]="NON_HOURLY_CROSS_STREAM_CLOCK_SKEW"
            return out
        out["six_crypto_lag_behind_BTC_hours"]=int(delta)
        if delta<0:
            out["status"]="BLOCKED"
            out["reason_code"]="SIX_CRYPTO_EVIDENCE_AHEAD_OF_BTC_FIRST_STREAM"
            return out

    side_hours=source["current_segment_independent_prospective_hours"]
    if type(side_hours) is not int or side_hours<0:
        out["reason_code"]="SIX_CRYPTO_PROSPECTIVE_COUNT_INVALID"
        return out
    if source["current_segment_prospective_asset_bar_count"]!=6*side_hours:
        out["reason_code"]="SIX_CRYPTO_ASSET_BAR_TO_CLOCK_HOUR_COUNT_MISMATCH"
        return out
    out["six_crypto_current_segment_independent_prospective_hours"]=side_hours
    out["six_crypto_current_segment_prospective_asset_bar_count"]=6*side_hours
    out["six_crypto_segment_index"]=source["segment_index"]
    out["six_crypto_historical_bootstrap_count"]=source[
        "historical_bootstrap_count"]
    out["six_crypto_ready_for_168_hour_audit"]=source[
        "ready_for_seven_day_audit"]

    if btc.get("status")=="PAUSED":
        out.update(status="BTC_PAUSED_SIDE_EVIDENCE_PRESERVED",
                   reason_code="BTC_DURABLE_PAUSE_PRESENT")
        return out
    if source.get("status")=="NO_UNIVERSE_EVIDENCE_YET":
        out.update(status="BTC_HEALTHY_SIX_CRYPTO_EMPTY_NAMESPACE",
                   reason_code="SIX_CRYPTO_FIRST_BASELINE_NOT_RECORDED")
        return out
    if side_hours==0:
        out.update(status="BTC_HEALTHY_SIX_CRYPTO_BASELINE_ONLY",
                   reason_code="SIX_CRYPTO_72H_BASELINE_COUNTS_ZERO_PROSPECTIVE")
        return out
    lag=out.get("six_crypto_lag_behind_BTC_hours")
    if isinstance(lag,int) and lag>0:
        out.update(status="BTC_HEALTHY_SIX_CRYPTO_BEHIND",
                   reason_code="SIX_CRYPTO_MISSED_OR_FAILED_LATEST_BTC_FIRST_TICK")
        return out

    if shadow.get("kind")!="OFFLINE_SIX_CRYPTO_SHA_CHAINED_SHADOW_ONLY":
        out.update(status="SIX_CRYPTO_SOURCE_VALID_SHADOW_NOT_CURRENT",
                   reason_code="LATEST_PROSPECTIVE_SOURCE_HAS_NO_VERIFIED_SHADOW")
        return out
    if shadow.get("current_segment_distinct_prospective_UTC_hours")!=side_hours:
        out.update(status="BLOCKED",
                   reason_code="SIX_CRYPTO_SOURCE_AND_SHADOW_COUNTS_DIVERGE")
        return out

    out.update(
        status=("SIX_CRYPTO_168_HOUR_CONTIGUOUS_EVIDENCE_READY"
                if source["ready_for_seven_day_audit"]
                else "BTC_AND_SIX_CRYPTO_CURRENTLY_ALIGNED"),
        reason_code="NONE",
        six_crypto_shadow_payload_sha256=shadow.get("shadow_payload_sha256"),
        six_crypto_strategy_promoted=False,
        future_edge_established=False)
    return out


def main(argv:list[str]|None=None) -> int:
    parser=argparse.ArgumentParser(
        description="OFFLINE BTC-first + six-crypto evidence status; no keys/network/orders.")
    parser.add_argument("--btc-root",type=Path,default=CLOUD_ROOT)
    parser.add_argument("--sidecar-root",type=Path,default=SHARED_VOLUME_SIDECAR_ROOT)
    args=parser.parse_args(argv)
    try:
        result=dual_forward_integrity_status(
            btc_root=args.btc_root,sidecar_root=args.sidecar_root)
        okay=result["status"] not in ("BLOCKED",)
    except Exception as exc:
        result={
            "kind":"OFFLINE_BTC_FIRST_SIX_CRYPTO_COMBINED_INTEGRITY_STATUS",
            "status":"BLOCKED",
            "reason_code":"COMBINED_STATUS_AUDIT_FAILED",
            "failure_class":type(exc).__name__,
            "network_requests":"NONE",
            "credentials_accessed":"NONE",
            "files_modified":False,
            "broker_order_submission":"DISABLED",
        }
        okay=False
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if okay else 2


if __name__=="__main__":
    raise SystemExit(main())

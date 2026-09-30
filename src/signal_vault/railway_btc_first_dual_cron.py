"""UNACTIVATED BTC-FIRST combined Railway cron using the EXISTING free volume.

The Railway Free plan currently permits only ONE volume in a project, and
the original BTC cron already uses it. This optional adapter can preserve the
original BTC forward journal while adding a physically separate 0700 source
namespace under that SAME persistent volume. NO new service/volume/credential
set, account connection, paid tier, SIP, paper orders or live trades.

CRITICAL: Merely merging does NOTHING: the current Docker CMD remains
python -m signal_vault.railway_forward_cron --once, NOT this module.
Activation requires an explicit owner-approved startCommand change AND an
exact opt-in flag. It runs the original BTC capture FIRST, then (if and only
if healthy/explicitly opted in) an independent bounded six-crypto DATA GET.
A sidecar exception never changes an already completed BTC receipt.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime,timezone
from pathlib import Path
from typing import Callable,Mapping

from .cloud_forward_service import CLOUD_ROOT
from .crypto_universe_forward import (
    SHARED_VOLUME_SIDECAR_ROOT,collect_six_crypto_once,_safe_root,
)
from .multi_asset_historical import BoundedAlpacaHistoricalBatch
from .railway_forward_cron import (
    configured_railway_volume,railway_data_credentials,railway_once,
)
from .six_crypto_shadow import archive_six_crypto_shadow

ACTIVATION_FLAG="SIGNAL_VAULT_SIX_CRYPTO_SIDECAR"
ACTIVATION_VALUE="BTC_FIRST_ISOLATED_DATA_GET_ONLY_NO_ORDERS_V1"
BASENAME="isolated-six-crypto-prospective"
# Sharing the physical Free 500MB volume requires an explicit, conservative
# headroom GUARANTEE for the original BTC stream before any six-asset GET.
# Reserve 128 MiB of physically available space exclusively for BTC and
# cap total new six-market immutable receipts/shadows to 32 MiB. Never
# delete/prune original BTC or new research evidence to reclaim space.
BTC_MINIMUM_FREE_RESERVE_BYTES=128*1024*1024
SIX_MARKET_TOTAL_EVIDENCE_CAP_BYTES=32*1024*1024
MAX_NEW_SIDECAR_TICK_BUDGET_BYTES=4*1024*1024


class SidecarStorageBudgetExceeded(ValueError):
    pass


def _sidecar_has_safe_storage_budget(
    *,verified_btc_root:Path,sidecar_root:Path,
) -> int:
    if sidecar_root.is_symlink() or not sidecar_root.is_dir():
        raise SidecarStorageBudgetExceeded("private six-market source dir unavailable")
    stats=os.statvfs(verified_btc_root)
    available=stats.f_bavail*stats.f_frsize
    if available < (BTC_MINIMUM_FREE_RESERVE_BYTES+
                    MAX_NEW_SIDECAR_TICK_BUDGET_BYTES):
        raise SidecarStorageBudgetExceeded("original BTC storage reserve cannot be guaranteed")
    total=0
    inspected=0
    for item in sidecar_root.rglob("*"):
        inspected+=1
        if inspected>30_000 or item.is_symlink():
            raise SidecarStorageBudgetExceeded("unsafe or excessive six-market storage tree")
        if item.is_file():
            total+=item.stat().st_size
            if total+MAX_NEW_SIDECAR_TICK_BUDGET_BYTES > SIX_MARKET_TOTAL_EVIDENCE_CAP_BYTES:
                raise SidecarStorageBudgetExceeded("six-market storage cap reached; preserve BTC")
        elif not item.is_dir():
            raise SidecarStorageBudgetExceeded("unexpected six-market evidence inode")
    return available


BTC_HEALTHY={
    "ONE_PROSPECTIVE_OBSERVATION_AND_SHADOW_ARCHIVED",
    "HISTORY_BOOTSTRAPPED_NO_RETROSPECTIVE_SHADOW",
    "SAFE_NO_NEW_OBSERVATION",
}


def _new_private_sidecar(*,verified_btc_root:Path,sidecar_root:Path) -> Path:
    if (verified_btc_root.is_symlink() or
            verified_btc_root.resolve()!=CLOUD_ROOT or
            sidecar_root!=verified_btc_root/BASENAME or
            sidecar_root.parent.resolve()!=verified_btc_root.resolve()):
        raise ValueError("only the exact dedicated sidecar under the attached BTC volume is allowed")
    if sidecar_root.is_symlink():
        raise ValueError("refusing existing six-market sidecar symlink")
    if not sidecar_root.exists():
        # Create ONLY the new empty logical evidence namespace. No recursive
        # parent creation, no chmod/migration/deletion of BTC journal files.
        os.mkdir(sidecar_root,0o700)
    return _safe_root(sidecar_root)


def combined_btc_first_once(
    *,now:datetime,environ:Mapping[str,str]|None=None,
    btc_root:Path=CLOUD_ROOT,
    sidecar_root:Path=SHARED_VOLUME_SIDECAR_ROOT,
    btc_runner:Callable[...,dict[str,object]]=railway_once,
    sidecar_provider_factory:Callable[[],object]|None=None,
    sidecar_clock:Callable[[],datetime]|None=None,
) -> dict[str,object]:
    """BTC forward first; optional six-asset source second; NO new credentials."""
    env=os.environ if environ is None else environ
    output:dict[str,object]={
        "kind":"RAILWAY_FREE_SINGLE_VOLUME_BTC_FIRST_SIX_CRYPTO_RESEARCH_CRON",
        "btc_status":"NOT_RUN",
        "sidecar_status":"NOT_ACTIVATED",
        "existing_BTC_evidence_deleted_or_reset":False,
        "new_Railway_service_created":False,
        "new_Railway_volume_created":False,
        "new_credential_values_required":False,
        "broker_order_submission":"DISABLED",
        "automatic_paper_trading":"DISABLED",
        "live_trading":"UNAVAILABLE",
        "credential_values_in_output":False,
    }
    try:
        verified=configured_railway_volume(
            environ=env,expected_root=btc_root,
            allow_owner_permission_repair=True)
    except Exception as exc:
        output.update(
            btc_status="BLOCKED_BTC_VOLUME_PREFLIGHT",
            failure_class=type(exc).__name__)
        return output
    try:
        stamp=now.astimezone(timezone.utc)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("timezone-aware original BTC scheduler clock required")
        # Keep EXACT existing BTC implementation unmodified. It has its own
        # durable pause, lock, shadow and no-replay policy and returns a
        # credential-free public receipt. Never skip BTC for sidecar work.
        btc=btc_runner(
            now=stamp,environ=env,expected_root=verified)
        if not isinstance(btc,dict) or not isinstance(btc.get("status"),str):
            raise ValueError("original BTC cron returned invalid status")
        output["btc_status"]=btc["status"]
        output["btc_prospective_observations_verified"]=btc.get(
            "prospective_observations_verified")
        output["btc_collector_decision"]=btc.get("collector_decision")
        output["btc_failure_class"]=btc.get("failure_class")
    except Exception as exc:
        output.update(btc_status="BLOCKED_ORIGINAL_BTC_CRON_EXCEPTION",
                      btc_failure_class=type(exc).__name__)
        return output

    if output["btc_status"] not in BTC_HEALTHY:
        output["sidecar_status"]="SKIPPED_BECAUSE_ORIGINAL_BTC_IS_NOT_HEALTHY"
        return output

    switch=env.get(ACTIVATION_FLAG,"")
    if switch=="":
        # No new directory, provider factory or DATA call by merely deploying
        # an image with this optional source module.
        return output
    if switch!=ACTIVATION_VALUE:
        output["sidecar_status"]="BLOCKED_UNRECOGNIZED_SIX_MARKET_OPT_IN"
        return output

    try:
        root=_new_private_sidecar(
            verified_btc_root=verified,sidecar_root=sidecar_root)
        _sidecar_has_safe_storage_budget(
            verified_btc_root=verified,sidecar_root=root)
        factory=sidecar_provider_factory
        if factory is None:
            def factory():
                # OLD dedicated BTC DATA-only pair reused within the SAME
                # existing isolated service. Never inspect/order via broker
                # host and NEVER copy credentials into source/receipt logs.
                creds=railway_data_credentials(environ=env)
                return BoundedAlpacaHistoricalBatch(
                    creds.key_id,creds.secret_key)
        clock=sidecar_clock() if sidecar_clock is not None else datetime.now(timezone.utc)
        source=collect_six_crypto_once(
            root=root,now=clock,provider_factory=factory)
        output["sidecar_status"]=source["status"]
        output["sidecar_recorded_prospective_asset_bars"]=source.get(
            "recorded_prospective_asset_bars",0)
        output["sidecar_recorded_distinct_prospective_UTC_hours"]=source.get(
            "recorded_distinct_prospective_UTC_hours",0)
        output["sidecar_source_SHA256"]=source.get("source_SHA256")
        if source["status"] in (
            "SIX_NEW_PROSPECTIVE_ASSET_BARS_ONE_CLOCK_HOUR",
            "SAFE_DUPLICATE_OR_CLOCK_ROLLBACK_NO_GET",
        ):
            # A same-clock duplicate repairs an interrupted shadow write,
            # not source bars. Do not try to archive a rolled-back future
            # hour if the current live clock is before recorded latest close.
            due=clock.astimezone(timezone.utc).replace(
                minute=0,second=0,microsecond=0).isoformat()
            if (source["status"]=="SIX_NEW_PROSPECTIVE_ASSET_BARS_ONE_CLOCK_HOUR" or
                    source.get("last_verified_close_utc")==due):
                try:
                    shadow=archive_six_crypto_shadow(root=root)
                    output["sidecar_shadow_status"]=shadow["status"]
                    output["sidecar_shadow_SHA256"]=shadow.get("shadow_payload_sha256")
                except Exception as exc:
                    output["sidecar_status"]="SOURCE_PRESERVED_SHADOW_REQUIRES_RETRY"
                    output["sidecar_shadow_failure_class"]=type(exc).__name__
    except SidecarStorageBudgetExceeded as exc:
        output.update(
            sidecar_status="SIX_MARKET_SKIPPED_TO_PRESERVE_BTC_DISK_RESERVE",
            sidecar_failure_class=type(exc).__name__,
            original_BTC_status_preserved=True)
    except Exception as exc:
        output.update(
            sidecar_status="FAILED_SAFE_OR_BLOCKED_NEW_SIDE_CAR_ONLY",
            sidecar_failure_class=type(exc).__name__,
            original_BTC_status_preserved=True)
    return output


def main(argv:list[str]|None=None) -> int:
    parser=argparse.ArgumentParser(
        description="UNACTIVATED optional BTC-first + six-crypto GET-only single-volume cron.")
    parser.add_argument("--once",action="store_true",required=True)
    parsed=parser.parse_args(argv)
    result=combined_btc_first_once(now=datetime.now(timezone.utc))
    print(json.dumps(result,sort_keys=True,indent=2))
    # Preserve original BTC cron health semantics; a six-market sidecar
    # failure is loudly and separately logged but never rolls back or
    # reclassifies the completed original BTC observation.
    return 0 if result["btc_status"] in BTC_HEALTHY else 2


if __name__=="__main__":
    raise SystemExit(main())

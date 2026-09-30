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

from .cloud_forward_service import CLOUD_ROOT,cloud_status
from .btc_evidence_fingerprint import (
    BtcEvidencePermissionError,fingerprint_btc_evidence_tree,
    restrict_btc_evidence_permissions,
)
from .crypto_universe_forward import (
    SHARED_VOLUME_SIDECAR_ROOT,collect_six_crypto_once,universe_status,_safe_root,
)
from .multi_asset_historical import BoundedAlpacaHistoricalBatch
from .railway_forward_cron import (
    configured_railway_volume,railway_data_credentials,railway_once,
)
from .six_crypto_shadow import (
    archive_six_crypto_shadow,audit_six_crypto_shadow_archive,
    inspect_six_crypto_shadow,
)
from .six_crypto_forward_scorecard import prospective_shadow_scorecard

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


def _sidecar_permission_snapshot(*,sidecar_root:Path) -> dict[str,object]:
    """Read-only minimal permission metadata for exact sidecar-owned entries."""
    out={"process_euid":os.geteuid(),"entries":{}}
    names=(".", ".six-crypto-source.lock", "hourly-receipts",
           "immutable-six-crypto-shadows")
    for name in names:
        item=sidecar_root if name=="." else sidecar_root/name
        entry={
            "exists":item.exists(),
            "symlink":item.is_symlink(),
        }
        if item.exists() and not item.is_symlink():
            st=item.stat()
            entry.update({
                "kind":("directory" if item.is_dir() else
                        "file" if item.is_file() else "other"),
                "mode_octal":format(st.st_mode&0o777,"04o"),
                "uid_matches_process":st.st_uid==os.geteuid(),
                "readable":os.access(item,os.R_OK),
                "writable":os.access(item,os.W_OK),
                "executable":os.access(item,os.X_OK),
            })
        out["entries"][name]=entry
    return out


def _restrict_known_sidecar_directories(*,sidecar_root:Path) -> list[str]:
    """Repair ONLY permission bits on exact direct child dirs we created.

    Railway persistent volumes can preserve owner-private contents while a
    directory mode drifts across runtime/image transitions. We never chmod
    the sidecar root itself here (an insecure root remains fail-closed), never
    follow symlinks, never touch original BTC paths, and never alter evidence
    file bytes. Root UID is required for any repair.
    """
    repaired=[]
    for name in ("hourly-receipts","immutable-six-crypto-shadows"):
        child=sidecar_root/name
        if child.is_symlink():
            raise ValueError("sidecar-owned directory cannot be a symlink")
        if not child.exists():
            continue
        if not child.is_dir():
            raise ValueError("sidecar-owned evidence namespace is not a directory")
        mode=child.stat().st_mode&0o777
        if mode!=0o700:
            if os.geteuid()!=0:
                raise PermissionError("sidecar child permission drift requires root-only restriction")
            os.chmod(child,0o700)
            if child.stat().st_mode&0o777!=0o700:
                raise PermissionError("could not restrict sidecar child directory to 0700")
            repaired.append(name)
    return repaired


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


def combined_offline_status(
    *,environ:Mapping[str,str]|None=None,
    btc_root:Path=CLOUD_ROOT,
    sidecar_root:Path=SHARED_VOLUME_SIDECAR_ROOT,
) -> dict[str,object]:
    """Read-only BTC + six-market progress. No DATA credentials or provider calls."""
    env=os.environ if environ is None else environ
    out:dict[str,object]={
        "kind":"RAILWAY_BTC_FIRST_SIX_CRYPTO_OFFLINE_STATUS",
        "status":"BLOCKED",
        "network_requests":"NONE",
        "credential_access":"NONE",
        "broker_order_submission":"DISABLED",
        "automatic_paper_trading":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
    try:
        verified=configured_railway_volume(
            environ=env,expected_root=btc_root,
            allow_owner_permission_repair=False)
        out["btc"]=cloud_status(root=verified)
        out["sidecar_activation_flag_present"]=(env.get(ACTIVATION_FLAG,"")!="")
        out["sidecar_activation_exact"]=(env.get(ACTIVATION_FLAG,"")==ACTIVATION_VALUE)
        if not out["sidecar_activation_exact"]:
            out["sidecar_status"]="NOT_ACTIVATED_OR_UNRECOGNIZED"
            out["status"]="READ_ONLY_BTC_STATUS_AVAILABLE"
            return out
        if not sidecar_root.exists():
            out["sidecar_status"]="ACTIVATED_BUT_BASELINE_NOT_CREATED_YET"
            out["status"]="READ_ONLY_STATUS_AVAILABLE"
            return out
        root=_safe_root(sidecar_root)
        source=universe_status(root=root)
        out["sidecar"]=source
        out["sidecar_status"]=source["status"]
        out["sidecar_current_segment_index"]=source["segment_index"]
        out["sidecar_current_segment_independent_prospective_hours"]=source[
            "current_segment_independent_prospective_hours"]
        out["sidecar_current_segment_prospective_asset_bar_count"]=source[
            "current_segment_prospective_asset_bar_count"]
        out["sidecar_latest_hour_utc"]=source["latest_hour_utc"]
        out["sidecar_ready_for_seven_day_audit"]=source["ready_for_seven_day_audit"]
        shadow=inspect_six_crypto_shadow(root=root)
        archive=audit_six_crypto_shadow_archive(root=root)
        out["sidecar_shadow_status"]=shadow.get("status",shadow.get("kind"))
        out["sidecar_shadow_archive_status"]=archive["status"]
        out["sidecar_current_segment_shadow_files_verified"]=archive[
            "current_segment_shadow_files_verified"]
        out["sidecar_current_segment_shadow_archive_complete"]=archive[
            "current_segment_shadow_archive_complete"]
        if source["current_segment_independent_prospective_hours"]>0:
            if shadow.get("kind")!="OFFLINE_SIX_CRYPTO_SHA_CHAINED_SHADOW_ONLY":
                raise ValueError("prospective six-market source lacks audited latest shadow")
            if (shadow.get("current_segment_distinct_prospective_UTC_hours")!=
                    source["current_segment_independent_prospective_hours"] or
                    shadow.get("latest_newly_observed_UTC_close")!=source["latest_hour_utc"]):
                raise ValueError("six-market source and shadow progress disagree")
            out["sidecar_latest_shadow_SHA256"]=shadow.get("shadow_payload_sha256")
        out["sidecar_source_168_hour_collection_ready"]=bool(
            source["ready_for_seven_day_audit"] and
            archive["current_segment_shadow_archive_complete"] and
            archive["current_segment_shadow_files_verified"]==
            source["current_segment_independent_prospective_hours"])
        score=prospective_shadow_scorecard(root=root)
        out["sidecar_scorecard_status"]=score["status"]
        out["sidecar_fully_observed_precommitted_decision_intervals"]=score[
            "fully_observed_precommitted_decision_intervals"]
        out["sidecar_full_168_precommitted_decision_outcomes_ready"]=score.get(
            "full_168_precommitted_decision_outcomes_ready",False)
        # Preserve older field name as SOURCE collection milestone only.
        out["sidecar_ready_for_seven_day_audit"]=out[
            "sidecar_source_168_hour_collection_ready"]
        out["status"]="READ_ONLY_STATUS_AVAILABLE"
        return out
    except Exception as exc:
        out.update(
            status="BLOCKED_OFFLINE_STATUS_AUDIT_FAILED",
            failure_class=type(exc).__name__)
        return out


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
        "sidecar_stage":"NOT_STARTED",
        "sidecar_directory_permissions_restricted":[],
        "btc_evidence_permission_modes_restricted":[],
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
        # BTC has already completed its own hourly transaction. Snapshot every
        # original BTC evidence byte NOW and compare after the sidecar stage,
        # excluding only the dedicated six-market child namespace.
        output["sidecar_stage"]="BTC_EVIDENCE_FINGERPRINT_BEFORE"
        try:
            btc_before_sidecar=fingerprint_btc_evidence_tree(
                verified,excluded_sidecar_name=BASENAME)
        except BtcEvidencePermissionError:
            # Restrict ONLY mode bits on root-owned BTC evidence. No evidence
            # bytes, names, ownership, or dedicated sidecar bytes are changed.
            output["sidecar_stage"]="BTC_EVIDENCE_PERMISSION_RESTRICTION"
            output["btc_evidence_permission_modes_restricted"]=(
                restrict_btc_evidence_permissions(
                    verified,excluded_sidecar_name=BASENAME))
            output["sidecar_stage"]="BTC_EVIDENCE_FINGERPRINT_BEFORE"
            btc_before_sidecar=fingerprint_btc_evidence_tree(
                verified,excluded_sidecar_name=BASENAME)
        output["btc_evidence_before_sidecar_SHA256"]=btc_before_sidecar[
            "tree_sha256"]
        output["btc_evidence_before_sidecar_file_count"]=btc_before_sidecar[
            "file_count"]
        output["sidecar_stage"]="SIDE_CAR_ROOT_VALIDATION"
        root=_new_private_sidecar(
            verified_btc_root=verified,sidecar_root=sidecar_root)
        output["sidecar_stage"]="SIDE_CAR_CHILD_PERMISSION_RESTRICTION"
        output["sidecar_directory_permissions_restricted"]=_restrict_known_sidecar_directories(
            sidecar_root=root)
        output["sidecar_stage"]="SIDE_CAR_STORAGE_BUDGET"
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
        output["sidecar_stage"]="SIX_CRYPTO_SOURCE_COLLECTION"
        source=collect_six_crypto_once(
            root=root,now=clock,provider_factory=factory)
        output["sidecar_status"]=source["status"]
        output["sidecar_recorded_prospective_asset_bars"]=source.get(
            "recorded_prospective_asset_bars",0)
        output["sidecar_recorded_distinct_prospective_UTC_hours"]=source.get(
            "recorded_distinct_prospective_UTC_hours",0)
        output["sidecar_source_SHA256"]=source.get("source_SHA256")
        output["sidecar_stage"]="SIX_CRYPTO_SOURCE_CHAIN_AUDIT"
        cumulative=universe_status(root=root)
        output["sidecar_current_segment_index"]=cumulative["segment_index"]
        output["sidecar_current_segment_independent_prospective_hours"]=cumulative[
            "current_segment_independent_prospective_hours"]
        output["sidecar_current_segment_prospective_asset_bar_count"]=cumulative[
            "current_segment_prospective_asset_bar_count"]
        output["sidecar_latest_hour_utc"]=cumulative["latest_hour_utc"]
        output["sidecar_ready_for_seven_day_audit"]=cumulative[
            "ready_for_seven_day_audit"]
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
                    output["sidecar_stage"]="SIX_CRYPTO_SHADOW_ARCHIVE"
                    shadow=archive_six_crypto_shadow(root=root)
                    output["sidecar_shadow_status"]=shadow["status"]
                    output["sidecar_shadow_SHA256"]=shadow.get("shadow_payload_sha256")
                except Exception as exc:
                    output["sidecar_status"]="SOURCE_PRESERVED_SHADOW_REQUIRES_RETRY"
                    output["sidecar_shadow_failure_class"]=type(exc).__name__
        output["sidecar_stage"]="BTC_EVIDENCE_FINGERPRINT_AFTER"
        btc_after_sidecar=fingerprint_btc_evidence_tree(
            verified,excluded_sidecar_name=BASENAME)
        output["btc_evidence_after_sidecar_SHA256"]=btc_after_sidecar[
            "tree_sha256"]
        output["btc_evidence_changed_during_sidecar_stage"]=(
            btc_after_sidecar["tree_sha256"]!=
            btc_before_sidecar["tree_sha256"])
        output["existing_BTC_evidence_deleted_or_reset"]=False
        if not output["btc_evidence_changed_during_sidecar_stage"]:
            output["sidecar_stage"]="COMPLETE"
        if output["btc_evidence_changed_during_sidecar_stage"]:
            output["sidecar_status"]="FAILED_BTC_EVIDENCE_MUTATION_GUARD"
            output["sidecar_failure_class"]="BtcEvidenceFingerprintMismatch"
            output["original_BTC_status_preserved"]=False
            output["existing_BTC_evidence_deleted_or_reset"]=None
    except SidecarStorageBudgetExceeded as exc:
        output.update(
            sidecar_status="SIX_MARKET_SKIPPED_TO_PRESERVE_BTC_DISK_RESERVE",
            sidecar_failure_class=type(exc).__name__,
            original_BTC_status_preserved=True)
        if "btc_before_sidecar" in locals():
            btc_after_sidecar=fingerprint_btc_evidence_tree(
                verified,excluded_sidecar_name=BASENAME)
            output["btc_evidence_after_sidecar_SHA256"]=btc_after_sidecar["tree_sha256"]
            output["btc_evidence_changed_during_sidecar_stage"]=(
                btc_after_sidecar["tree_sha256"]!=btc_before_sidecar["tree_sha256"])
    except Exception as exc:
        output.update(
            sidecar_status="FAILED_SAFE_OR_BLOCKED_NEW_SIDE_CAR_ONLY",
            sidecar_failure_class=type(exc).__name__,
            original_BTC_status_preserved=True)
        if isinstance(exc,BtcEvidencePermissionError):
            output["btc_permission_failure_path"]=exc.relative_path
            output["btc_permission_failure_kind"]=exc.kind
            output["btc_permission_failure_mode_octal"]=format(exc.mode,"04o")
            output["btc_permission_failure_diagnostic_only"]=True
        try:
            output["sidecar_permission_snapshot"]=_sidecar_permission_snapshot(
                sidecar_root=sidecar_root)
        except Exception as snapshot_exc:
            output["sidecar_permission_snapshot_failure_class"]=type(
                snapshot_exc).__name__
        if "btc_before_sidecar" in locals():
            try:
                btc_after_sidecar=fingerprint_btc_evidence_tree(
                    verified,excluded_sidecar_name=BASENAME)
                output["btc_evidence_after_sidecar_SHA256"]=btc_after_sidecar[
                    "tree_sha256"]
                output["btc_evidence_changed_during_sidecar_stage"]=(
                    btc_after_sidecar["tree_sha256"]!=
                    btc_before_sidecar["tree_sha256"])
                if output["btc_evidence_changed_during_sidecar_stage"]:
                    output["sidecar_status"]="FAILED_BTC_EVIDENCE_MUTATION_GUARD"
                    output["sidecar_failure_class"]="BtcEvidenceFingerprintMismatch"
                    output["original_BTC_status_preserved"]=False
                    output["existing_BTC_evidence_deleted_or_reset"]=None
            except Exception as fingerprint_exc:
                output["btc_evidence_integrity_recheck_failure_class"]=type(
                    fingerprint_exc).__name__
    return output


def main(argv:list[str]|None=None) -> int:
    parser=argparse.ArgumentParser(
        description="BTC-first + six-crypto GET-only single-volume cron / read-only status.")
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--once",action="store_true")
    modes.add_argument("--status",action="store_true")
    parsed=parser.parse_args(argv)
    if parsed.status:
        result=combined_offline_status()
        code=0 if result["status"] in (
            "READ_ONLY_STATUS_AVAILABLE","READ_ONLY_BTC_STATUS_AVAILABLE") else 2
    else:
        result=combined_btc_first_once(now=datetime.now(timezone.utc))
        # Preserve original BTC cron health semantics; a six-market sidecar
        # failure is loudly and separately logged but never rolls back or
        # reclassifies the completed original BTC observation.
        code=0 if result["btc_status"] in BTC_HEALTHY else 2
    print(json.dumps(result,sort_keys=True,indent=2))
    return code


if __name__=="__main__":
    raise SystemExit(main())

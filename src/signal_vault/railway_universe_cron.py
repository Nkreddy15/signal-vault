"""Not activated: OPTIONAL second Railway cron adapter for six crypto DATA only.

This module is deliberately not referenced by Dockerfile, existing BTC
cron, existing Railway service, account/portfolio reader or trading code.
A future independently approved SERVICE requires its OWN mounted root
/var/lib/signal-vault/forward-universe and OWN dedicated two DATA vars.
Never reuse BTC's persistent evidence directory or mix those prospective
samples. No new service, credentials, API call, expense or cron is created
merely by merging this adapter.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime,timezone
from pathlib import Path
from typing import Callable, Mapping

from .crypto_universe_forward import (
    ROOT, collect_six_crypto_once, universe_status, _safe_root,
)
from .multi_asset_historical import BoundedAlpacaHistoricalBatch
from .paper_credentials import PaperCredentials
from .six_crypto_shadow import archive_six_crypto_shadow
from .unattended_forward_cycle import FORBIDDEN_ENV

KEY="SIGNAL_VAULT_UNIVERSE_DATA_KEY_ID"
SECRET="SIGNAL_VAULT_UNIVERSE_DATA_SECRET"
MOUNT="RAILWAY_VOLUME_MOUNT_PATH"
FORBIDDEN=FORBIDDEN_ENV+(
    "ALPACA_PAPER_KEY_ID","ALPACA_PAPER_SECRET_KEY",
    "SIGNAL_VAULT_FORWARD_DATA_KEY_ID","SIGNAL_VAULT_FORWARD_DATA_SECRET",
    "SIGNAL_VAULT_ENABLE_PAPER_ORDERS","SIGNAL_VAULT_MODE",
)


def mounted_universe_volume(
    *,environ:Mapping[str,str],expected_root:Path=ROOT,
    allow_owner_permission_repair:bool=False,
) -> Path:
    if (str(environ.get(MOUNT,""))!=str(expected_root) or
            str(environ.get("RAILWAY_RUN_UID",""))!="0"):
        raise ValueError("a SECOND explicitly mounted Railway DATA volume is required")
    if expected_root.is_symlink() or not expected_root.is_dir():
        raise ValueError("six-market evidence volume must be a real mounted directory")
    if expected_root.stat().st_mode&0o077:
        if (not allow_owner_permission_repair or os.geteuid()!=0):
            raise PermissionError("isolated six-market volume must be owner-private")
        # Railway initially mounts its own empty dedicated volume as root.
        # Restrict ONLY this exact separately verified NEW mount directory.
        # NEVER chmod the BTC volume, any parents, source or receipt files.
        expected_root.chmod(0o700)
    return _safe_root(expected_root)


def _private_named_data_pair(*,environ:Mapping[str,str]) -> PaperCredentials:
    if any(str(environ.get(name,"")).strip() for name in FORBIDDEN):
        raise ValueError("broker/live/old BTC DATA variables forbidden for six-market worker")
    key,secret=environ.get(KEY),environ.get(SECRET)
    if (not isinstance(key,str) or not isinstance(secret,str) or
            not key or not secret or key!=key.strip() or secret!=secret.strip()
            or len(key)>512 or len(secret)>512):
        raise ValueError("new purpose-scoped DATA variable names are unavailable")
    return PaperCredentials(key,secret)


def universe_railway_preflight(
    *,environ:Mapping[str,str],expected_root:Path=ROOT,
) -> dict[str,object]:
    """No provider request, no credential values or root mutations."""
    result={
        "kind":"UNIVERSE_RAILWAY_SECOND_SERVICE_PREFLIGHT_ONLY",
        "status":"BLOCKED",
        "service_created_by_this_code":False,
        "old_BTC_journal_modified":False,
        "network_requests":"NONE",
        "broker_order_submission":"DISABLED",
        "credential_values_in_output":False,
    }
    try:
        root=mounted_universe_volume(
            environ=environ,expected_root=expected_root)
        _private_named_data_pair(environ=environ)
        verified=universe_status(root=root)
        result.update(status="SEPARATE_SIX_CRYPTO_SOURCE_READY",
                      evidence=verified)
    except Exception as exc:
        result.update(reason_code="NEW_VOLUME_OR_DATA_VARIABLES_NOT_READY",
                      failure_class=type(exc).__name__)
    return result


def universe_railway_once(
    *,environ:Mapping[str,str],now:datetime,
    expected_root:Path=ROOT,
    provider_factory:Callable[[],object]|None=None,
) -> dict[str,object]:
    """Only a separately configured service may actually invoke a DATA GET."""
    out={
        "kind":"RAILWAY_ISOLATED_SIX_CRYPTO_GET_ONLY_CRON",
        "status":"BLOCKED",
        "old_BTC_collector_modified":False,
        "market":"crypto",
        "broker_order_submission":"DISABLED",
        "automatic_paper_trading":"DISABLED",
        "credential_values_in_output":False,
    }
    try:
        root=mounted_universe_volume(
            environ=environ,expected_root=expected_root,
            allow_owner_permission_repair=True)
        if any(str(environ.get(name,"")).strip() for name in FORBIDDEN):
            raise ValueError("broker/live/BTC variables forbidden in new six-crypto source")
        if not environ.get(KEY) or not environ.get(SECRET):
            raise ValueError("purpose-scoped DATA variable names not configured")
        factory=provider_factory
        if factory is None:
            # The private pair is read only AFTER this module's volume/env
            # preflight and crypto_universe_forward's intact SHA-chain and
            # exact scheduled UTC time checks.
            def factory():
                creds=_private_named_data_pair(environ=environ)
                return BoundedAlpacaHistoricalBatch(
                    creds.key_id,creds.secret_key)
        result=collect_six_crypto_once(
            root=root,now=now,provider_factory=factory)
        out.update(result)
        # Source evidence is separately and DURABLY committed first. A
        # post-commit shadow error must not silently claim the source was
        # never recorded or re-fetch the same closed market bar. A safe
        # same-hour duplicate can independently retry the failed archive
        # with ZERO additional provider requests.
        current_hour=now.astimezone(timezone.utc).replace(
            minute=0,second=0,microsecond=0).isoformat()
        should_shadow=(
            result["status"]=="SIX_NEW_PROSPECTIVE_ASSET_BARS_ONE_CLOCK_HOUR" or
            (result["status"]=="SAFE_DUPLICATE_OR_CLOCK_ROLLBACK_NO_GET" and
             result.get("last_verified_close_utc")==current_hour))
        if should_shadow:
            try:
                receipt=archive_six_crypto_shadow(root=root)
                out["shadow_receipt_status"]=receipt["status"]
                out["shadow_payload_sha256"]=receipt.get("shadow_payload_sha256")
            except Exception as shadow_exc:
                out.update(
                    status="SOURCE_COMMITTED_SHADOW_ARCHIVE_BLOCKED_SAFE_TO_RETRY",
                    shadow_failure_class=type(shadow_exc).__name__,
                    source_receipt_still_preserved=True,
                    broker_order_submission="DISABLED")
    except Exception as exc:
        out.update(status="BLOCKED_NO_NEW_PROSPECTIVE_EVIDENCE",
                   reason_code="SIX_MARKET_VOLUME_SOURCE_OR_CHAIN_FAILED_CLOSED",
                   failure_class=type(exc).__name__)
    return out


def main(argv:list[str]|None=None) -> int:
    parser=argparse.ArgumentParser(
        description="Separate OPTIONAL Railway 6-crypto hourly GET-only adapter; NO orders.")
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight",action="store_true")
    modes.add_argument("--status",action="store_true")
    modes.add_argument("--once",action="store_true")
    args=parser.parse_args(argv)
    env=os.environ
    if args.preflight:
        out=universe_railway_preflight(environ=env)
        okay=out["status"]=="SEPARATE_SIX_CRYPTO_SOURCE_READY"
    elif args.status:
        try:
            root=mounted_universe_volume(environ=env)
            out=universe_status(root=root)
            okay=True
        except Exception as exc:
            out={
                "status":"BLOCKED_OFFLINE_UNIVERSE_EVIDENCE_UNAVAILABLE",
                "failure_class":type(exc).__name__,
                "network_requests":"NONE",
                "credential_values_in_output":False,
                "broker_order_submission":"DISABLED",
            }
            okay=False
    else:
        out=universe_railway_once(
            environ=env,now=datetime.now(timezone.utc))
        okay=out["status"] in (
            "HISTORICAL_BASELINE_ONLY_ZERO_PROSPECTIVE",
            "SIX_NEW_PROSPECTIVE_ASSET_BARS_ONE_CLOCK_HOUR",
            "SAFE_SKIP_OUTSIDE_FRESH_CLOSED_HOUR_WINDOW",
            "SAFE_DUPLICATE_OR_CLOCK_ROLLBACK_NO_GET",
        )
    print(json.dumps(out,indent=2,sort_keys=True))
    return 0 if okay else 2


if __name__=="__main__":
    raise SystemExit(main())

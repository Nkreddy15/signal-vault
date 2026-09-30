"""Keyless six-symbol shadow decisions from ONLY verified multi-forward receipts.

No provider, Railway env, secret, account, order or market-data call here.
An initial 72h source baseline produces NO retrospective shadow. After one
new fresh six-crypto observation, reconstruct the current independent
segment; compute fixed four hypothesis decisions for both FLAT and HELD
hypothetical states at the NEXT bar's open, never assert account position.
Create-only 0600 private SHA-bound receipt, idempotent crash recovery.

A BUY/SELL label is a synthetic strategy ACTION, not an order permission or
validated forecasting edge. Historical bootstrap contributes indicator
warmup only, never a new prospective observation in this receipt.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import replace
from datetime import datetime,timezone
from pathlib import Path

from .crypto_universe_forward import (
    CRYPTO_SIX, ROOT, _audit_chain, _raw_bar, _safe_root, _utc,
    _sha,
)
from .multi_asset_simulation import HYPOTHESES,decide_on_prior_closes
from .research_universe import candidate,validate_asset_dataset
from .runtime_lock import RuntimeFileLock

FOLDER="immutable-six-crypto-shadows"
SHADOW_NAME=re.compile(r"shadow-hour-[0-9]{8}T[0-9]{4}Z\.json\Z")


def _safe_folder(root:Path,*,create:bool=False) -> Path:
    path=root/FOLDER
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError("shadow folder is not a real private directory")
    if create:
        path.mkdir(mode=0o700,exist_ok=True)
    if path.exists() and path.stat().st_mode&0o077:
        raise PermissionError("shadow folder must be private (0700)")
    return path


def _latest_payload(chain:list[dict[str,object]]) -> dict[str,object]|None:
    if not chain or chain[-1]["event"]!="ONE_NEW_CONTIGUOUS_PROSPECTIVE_HOUR":
        return None
    active=[r for r in chain if r["segment_index"]==chain[-1]["segment_index"]]
    if (not active or active[0]["event"]!="HISTORICAL_72H_BOOTSTRAP" or
            any(x["event"]!="ONE_NEW_CONTIGUOUS_PROSPECTIVE_HOUR" for x in active[1:])):
        raise ValueError("prospective shadow must have one contiguous verified baseline")
    latest=active[-1]
    close=_utc(datetime.fromisoformat(latest["closed_hour_utc"]))
    clock=_utc(datetime.fromisoformat(latest["captured_utc"]))
    historical_count=len(active[0]["source_historical_batch"]["bars"][CRYPTO_SIX[0]])
    if historical_count!=72:
        raise ValueError("current segment lacks the exact historical-only 72h warmup")
    signals={}
    reviews={}
    for sym in CRYPTO_SIX:
        bars=[]
        for i,receipt in enumerate(active):
            source=receipt["source_historical_batch"]["bars"][sym]
            for one in source:
                original=_raw_bar(one)
                bars.append(replace(original,prospective=(i>0)))
        dataset=tuple(bars)
        review=validate_asset_dataset(dataset,spec=candidate(sym),as_of=clock)
        if (review.historical_bars!=72 or
                review.prospective_bars!=len(active)-1 or
                dataset[-1].closed_utc!=close):
            raise ValueError("new shadow does not have independently verified prospectivity")
        reviews[sym]={
            "full_segment_dataset_sha256":review.content_sha256,
            "historical_warmup_bars":review.historical_bars,
            "genuinely_prospective_observed_bars":review.prospective_bars,
            "feed":review.feed,
        }
        named={}
        for hypothesis in HYPOTHESES:
            scenario={}
            for held in (False,True):
                decision=decide_on_prior_closes(
                    dataset,config=hypothesis,has_position=held,
                    next_open_utc=close)
                if decision.evaluated_close_utc!=close.isoformat():
                    raise ValueError("decision looked at incorrect or future close")
                scenario["already_held" if held else "flat"]={
                    "hypothetical_action":decision.action.value,
                    "evidence_sha256":decision.evidence_sha256,
                    "evaluated_last_completed_utc":decision.evaluated_close_utc,
                    "broker_order_submission":"DISABLED",
                }
            named[hypothesis.name]=scenario
        signals[sym]=named
    return {
        "kind":"OFFLINE_SIX_CRYPTO_SHA_CHAINED_SHADOW_ONLY",
        "schema_version":1,
        "latest_universe_source_receipt_SHA256":latest["receipt_sha256"],
        "last_source_provider_batch_SHA256":latest["source_batch_sha256"],
        "segment_index":latest["segment_index"],
        "latest_newly_observed_UTC_close":close.isoformat(),
        "current_segment_distinct_prospective_UTC_hours":len(active)-1,
        "current_segment_prospective_asset_bars":6*(len(active)-1),
        "asset_reviews":reviews,
        "predeclared_flat_and_held_hypothetical_decisions":signals,
        "retrospective_72h_history_counted_as_new_forward":False,
        "factual_broker_positions_queried":False,
        "strategy_promoted":False,
        "future_edge_established":False,
        "network_requests":"NONE",
        "credential_access":"NONE",
        "broker_order_submission":"DISABLED",
        "automatic_paper_trading":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


def _expected_shadow_entries(
    chain:list[dict[str,object]],
) -> list[tuple[Path,bytes,dict[str,object]]]:
    """Deterministically reconstruct every prospective shadow from source receipts."""
    expected=[]
    for index,receipt in enumerate(chain):
        if receipt["event"]!="ONE_NEW_CONTIGUOUS_PROSPECTIVE_HOUR":
            continue
        payload=_latest_payload(chain[:index+1])
        if payload is None:
            raise ValueError("prospective source receipt has no derivable shadow")
        payload["shadow_payload_sha256"]=_sha(payload)
        stamp=_utc(datetime.fromisoformat(payload["latest_newly_observed_UTC_close"]))
        name=Path("shadow-hour-"+stamp.strftime("%Y%m%dT%H%MZ")+".json")
        raw=(json.dumps(payload,sort_keys=True,indent=2)+"\n").encode("utf-8")
        expected.append((name,raw,payload))
    return expected


def audit_six_crypto_shadow_archive(*,root:Path=ROOT) -> dict[str,object]:
    """Read-only all-segment source→shadow parity. Missing is incomplete, tamper raises."""
    base=_safe_root(Path(root))
    chain=_audit_chain(base)
    expected=_expected_shadow_entries(chain)
    folder=_safe_folder(base)
    actual={}
    if folder.exists():
        for file in folder.iterdir():
            if (file.is_symlink() or not file.is_file() or
                    not SHADOW_NAME.fullmatch(file.name) or
                    file.stat().st_mode&0o077 or
                    not 0<file.stat().st_size<=2_000_000):
                raise ValueError("unexpected or insecure six-market shadow archive entry")
            actual[file.name]=file
    missing=[]
    for name,raw,_ in expected:
        file=actual.get(name.name)
        if file is None:
            missing.append(name.name)
        elif file.read_bytes()!=raw:
            raise ValueError("immutable six-market shadow differs from source-derived payload")
    expected_names={name.name for name,_,_ in expected}
    extras=sorted(set(actual)-expected_names)
    if extras:
        raise ValueError("shadow archive contains receipt not derivable from source chain")
    segment=chain[-1]["segment_index"] if chain else 0
    current_expected=sum(
        receipt["event"]=="ONE_NEW_CONTIGUOUS_PROSPECTIVE_HOUR" and
        receipt["segment_index"]==segment
        for receipt in chain)
    current_missing=sum(
        name.name in missing and payload["segment_index"]==segment
        for name,_,payload in expected)
    return {
        "kind":"OFFLINE_SIX_CRYPTO_ALL_SHADOWS_SOURCE_PARITY_AUDIT",
        "status":"COMPLETE" if not missing else "INCOMPLETE_MISSING_DERIVED_SHADOWS",
        "total_source_prospective_hours":len(expected),
        "total_shadow_files_verified":len(expected)-len(missing),
        "missing_shadow_files":missing,
        "current_segment_index":segment,
        "current_segment_source_prospective_hours":current_expected,
        "current_segment_shadow_files_verified":current_expected-current_missing,
        "current_segment_shadow_archive_complete":current_missing==0,
        "network_requests":"NONE",
        "credential_access":"NONE",
        "broker_order_submission":"DISABLED",
    }


def repair_six_crypto_shadow_archive(*,root:Path=ROOT) -> dict[str,object]:
    """Keyless crash recovery: create ONLY missing deterministic derived shadows."""
    base=_safe_root(Path(root))
    with RuntimeFileLock(base/".six-crypto-source.lock"):
        chain=_audit_chain(base)
        folder=_safe_folder(base,create=bool(
            any(r["event"]=="ONE_NEW_CONTIGUOUS_PROSPECTIVE_HOUR" for r in chain)))
        created=0
        latest_sha=None
        for name,raw,payload in _expected_shadow_entries(chain):
            file=folder/name
            if file.exists() or file.is_symlink():
                if (file.is_symlink() or not file.is_file() or
                        file.stat().st_mode&0o077 or file.read_bytes()!=raw):
                    raise ValueError("immutable shadow source/receipt conflict")
            else:
                fd=os.open(
                    file,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
                    getattr(os,"O_NOFOLLOW",0),0o600)
                with os.fdopen(fd,"wb") as output:
                    os.fchmod(output.fileno(),0o600)
                    output.write(raw);output.flush();os.fsync(output.fileno())
                created+=1
            latest_sha=payload["shadow_payload_sha256"]
        if folder.exists():
            directory_fd=os.open(
                folder,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        audited=audit_six_crypto_shadow_archive(root=base)
        return {
            "kind":"OFFLINE_SIX_MARKET_SHADOW_ARCHIVE_REPAIR",
            "status":("COMPLETE_NEW_DERIVED_SHADOWS_WRITTEN"
                      if created else "COMPLETE_ALREADY_ARCHIVED"),
            "new_shadow_files_written":created,
            "latest_shadow_payload_sha256":latest_sha,
            **{k:v for k,v in audited.items() if k not in ("kind","status")},
        }


def inspect_six_crypto_shadow(*,root:Path=ROOT) -> dict[str,object]:
    """Read-only full source chain and latest shadow decisions; ZERO writes."""
    base=_safe_root(Path(root))
    chain=_audit_chain(base)
    payload=_latest_payload(chain)
    if payload is None:
        return {
            "status":"NO_GENUINE_PROSPECTIVE_SIX_MARKET_HOUR_TO_EVALUATE",
            "historical_shadow_created":False,
            "network_requests":"NONE",
            "broker_order_submission":"DISABLED",
        }
    payload["shadow_payload_sha256"]=_sha(payload)
    return payload


def archive_six_crypto_shadow(*,root:Path=ROOT) -> dict[str,object]:
    """Backward-compatible latest-shadow call, now repairs any older missing derived shadow."""
    base=_safe_root(Path(root))
    inspected=inspect_six_crypto_shadow(root=base)
    if inspected.get("status")=="NO_GENUINE_PROSPECTIVE_SIX_MARKET_HOUR_TO_EVALUATE":
        return {
            "status":"NO_NEW_PROSPECTIVE_HOUR_NO_RETROSPECTIVE_SHADOW",
            "broker_order_submission":"DISABLED",
            "network_requests":"NONE",
        }
    repaired=repair_six_crypto_shadow_archive(root=base)
    return {
        "kind":"OFFLINE_SIX_MARKET_SHADOW_ARCHIVE_RESULT",
        "status":("NEW_IMMUTABLE_SIX_MARKET_SHADOW"
                  if repaired["new_shadow_files_written"] else
                  "ALREADY_ARCHIVED_IDENTICAL"),
        "latest_prospective_close_utc":
            inspected["latest_newly_observed_UTC_close"],
        "shadow_payload_sha256":inspected["shadow_payload_sha256"],
        "current_segment_distinct_prospective_UTC_hours":
            inspected["current_segment_distinct_prospective_UTC_hours"],
        "all_source_derived_shadows_complete":
            repaired["current_segment_shadow_archive_complete"],
        "new_data_requests_during_shadow":"NONE",
        "credentials_accessed":"NONE",
        "broker_order_submission":"DISABLED",
    }

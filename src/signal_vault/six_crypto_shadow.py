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
                if decision.bar_closed_utc!=close.isoformat():
                    raise ValueError("decision looked at incorrect or future close")
                scenario["already_held" if held else "flat"]={
                    "hypothetical_action":decision.action.value,
                    "evidence_sha256":decision.evidence_sha256,
                    "evaluated_last_completed_utc":decision.bar_closed_utc,
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
    """Safe retry after source receipt has committed but shadow archiving crashed."""
    base=_safe_root(Path(root))
    with RuntimeFileLock(base/".six-crypto-source.lock"):
        payload=_latest_payload(_audit_chain(base))
        if payload is None:
            return {
                "status":"NO_NEW_PROSPECTIVE_HOUR_NO_RETROSPECTIVE_SHADOW",
                "broker_order_submission":"DISABLED",
                "network_requests":"NONE",
            }
        payload["shadow_payload_sha256"]=_sha(payload)
        stamp=_utc(datetime.fromisoformat(payload["latest_newly_observed_UTC_close"]))
        name="shadow-hour-"+stamp.strftime("%Y%m%dT%H%MZ")+".json"
        folder=_safe_folder(base,create=True)
        file=folder/name
        raw=(json.dumps(payload,sort_keys=True,indent=2)+"\n").encode("utf-8")
        if file.exists() or file.is_symlink():
            if (file.is_symlink() or not file.is_file() or
                    file.stat().st_mode&0o077 or file.read_bytes()!=raw):
                raise ValueError("immutable shadow source/receipt conflict")
            action="ALREADY_ARCHIVED_IDENTICAL"
        else:
            fd=os.open(
                file,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
                getattr(os,"O_NOFOLLOW",0),0o600)
            with os.fdopen(fd,"wb") as output:
                os.fchmod(output.fileno(),0o600)
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            directory_fd=os.open(folder,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            action="NEW_IMMUTABLE_SIX_MARKET_SHADOW"
        return {
            "kind":"OFFLINE_SIX_MARKET_SHADOW_ARCHIVE_RESULT",
            "status":action,
            "latest_prospective_close_utc":
                payload["latest_newly_observed_UTC_close"],
            "shadow_payload_sha256":payload["shadow_payload_sha256"],
            "current_segment_distinct_prospective_UTC_hours":
                payload["current_segment_distinct_prospective_UTC_hours"],
            "new_data_requests_during_shadow":"NONE",
            "credentials_accessed":"NONE",
            "broker_order_submission":"DISABLED",
        }

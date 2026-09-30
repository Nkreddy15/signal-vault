"""Independent six-crypto prospective DATA-GET observations, no broker access.

This is a SIDE-BY-SIDE candidate for a FUTURE isolated persistent worker:
never import, reuse, migrate, reset, overwrite or alter the existing
BTC-only Railway forward journal/volume. It is NOT deployed merely by a
GitHub merge. The first fresh 72-hour pull is HISTORICAL baseline (zero
prospective); each subsequently and contiguously observed closed hour may
add exactly six prospective asset-bars / ONE independent clock-hour.

An actual source page is STILL a retrospective DATA endpoint read. A new
forward classification is only from this collector's fresh, append-only
hourly observation with a plausible real capture time and verified chain.
Local hash chains are unsigned integrity evidence, not an independent
provider signature. Zero account reads, zero order path or network in audit.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Mapping

from .multi_asset_historical import HistoricalDataBatch
from .research_universe import (
    AssetClass, ResearchBar, RESEARCH_CANDIDATES, candidate,
    validate_asset_dataset,
)
from .runtime_lock import RuntimeFileLock

HOUR=timedelta(hours=1)
BOOTSTRAP_HOURS=72
ROOT=Path("/var/lib/signal-vault/forward-universe")
EXISTING_BTC_ROOT=Path("/var/lib/signal-vault/forward")
# The Railway FREE plan permits only one persistent volume/project. This
# allowlisted sibling LOGICAL namespace may live INSIDE the already attached
# BTC volume, but it is never the BTC root or ANY of the original source,
# capture, state, pause, journal or shadow files. Only an explicitly enabled
# BTC-FIRST combined cron may create this subdirectory after verifying the
# existing volume itself. All other nested names remain forbidden.
SHARED_VOLUME_SIDECAR_ROOT=EXISTING_BTC_ROOT/"isolated-six-crypto-prospective"
FILENAME=re.compile(r"hour-[0-9]{8}T[0-9]{4}Z\.json\Z")
CRYPTO_SIX=tuple(sorted(
    c.symbol for c in RESEARCH_CANDIDATES
    if c.asset_class==AssetClass.CRYPTO))
if len(CRYPTO_SIX)!=6:
    raise RuntimeError("explicit bounded six-crypto candidate set changed")


def _utc(value:datetime) -> datetime:
    if not isinstance(value,datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware collector time required")
    return value.astimezone(timezone.utc)


def _safe_root(root:Path) -> Path:
    if root.is_symlink() or not root.is_dir() or root.stat().st_mode&0o077:
        raise ValueError("NEW SEPARATE nonsymlink 0700 persistent universe root required")
    absolute=root.resolve()
    if absolute in (EXISTING_BTC_ROOT,EXISTING_BTC_ROOT.parent):
        raise ValueError("six-asset collection cannot use the existing BTC journal root")
    if absolute.is_relative_to(EXISTING_BTC_ROOT):
        if (absolute!=SHARED_VOLUME_SIDECAR_ROOT or
                root.parent.resolve()!=EXISTING_BTC_ROOT or
                root.parent.stat().st_mode&0o077):
            raise ValueError("only the exact separate BTC-volume sidecar namespace is permitted")
    if not os.access(root,os.R_OK|os.W_OK|os.X_OK):
        raise PermissionError("isolated universe evidence root not writable")
    return root


def _receipt_folder(root:Path, *, create:bool=False) -> Path:
    folder=root/"hourly-receipts"
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise ValueError("receipt folder cannot be a file or symlink")
    if create:
        folder.mkdir(mode=0o700,exist_ok=True)
    if folder.exists() and folder.stat().st_mode&0o077:
        raise PermissionError("isolated source receipts must have 0700 permissions")
    return folder


def _sha(payload:object) -> str:
    return hashlib.sha256(
        (json.dumps(payload,sort_keys=True,separators=(",",":"))+"\n")
        .encode("utf-8")).hexdigest()


def _raw_bar(data:Mapping[str,object]) -> ResearchBar:
    if set(data)!={
            "symbol","start_utc","closed_utc","open","high","low","close",
            "volume","feed","captured_utc","prospective"}:
        raise ValueError("malformed or extra source bar fields")
    if data["prospective"] is not False:
        raise ValueError("provider's raw HISTORICAL capture cannot self-certify forward evidence")
    bar=ResearchBar(
        symbol=data["symbol"],
        start_utc=_utc(datetime.fromisoformat(data["start_utc"])),
        open=Decimal(data["open"]),
        high=Decimal(data["high"]),
        low=Decimal(data["low"]),
        close=Decimal(data["close"]),
        volume=Decimal(data["volume"]),
        feed=data["feed"],
        captured_utc=_utc(datetime.fromisoformat(data["captured_utc"])),
        prospective=False)
    if bar.to_dict()!=dict(data):
        raise ValueError("source record must have canonical unaltered UTC/decimal bars")
    return bar


def _audit_one(item:Mapping[str,object],previous:Mapping[str,object]|None) -> None:
    fields={
        "kind","schema_version","event","closed_hour_utc","captured_utc",
        "segment_index","previous_receipt_sha256","source_batch_sha256",
        "source_historical_batch","per_asset_observation_sha256",
        "prospective_asset_rows_in_this_receipt","distinct_prospective_hours_in_this_receipt",
        "broker_order_submission","automatic_paper_trading","live_trading",
        "receipt_sha256",
    }
    if (not isinstance(item,dict) or set(item)!=fields or
            item["kind"]!="ISOLATED_SIX_CRYPTO_HOURLY_DATA_ONLY_RECEIPT" or
            item["schema_version"]!=1 or
            item["broker_order_submission"]!="DISABLED" or
            item["automatic_paper_trading"]!="DISABLED" or
            item["live_trading"]!="UNAVAILABLE"):
        raise ValueError("unsafe or malformed multi-asset receipt schema")
    body={k:v for k,v in item.items() if k!="receipt_sha256"}
    if _sha(body)!=item["receipt_sha256"]:
        raise ValueError("multi-market immutable receipt digest differs")
    close=_utc(datetime.fromisoformat(item["closed_hour_utc"]))
    stamped=_utc(datetime.fromisoformat(item["captured_utc"]))
    if (close!=close.replace(minute=0,second=0,microsecond=0) or
            stamped.replace(minute=0,second=0,microsecond=0)!=close or
            not 3<=stamped.minute<25):
        raise ValueError("stale or implausibly early prospective observation")
    if previous is None:
        if (item["event"]!="HISTORICAL_72H_BOOTSTRAP" or
                item["segment_index"]!=1 or
                item["previous_receipt_sha256"] is not None):
            raise ValueError("chain must start at an explicitly zero-prospective baseline")
    else:
        prev_close=_utc(datetime.fromisoformat(previous["closed_hour_utc"]))
        if (close<=prev_close or
                item["previous_receipt_sha256"]!=previous["receipt_sha256"]):
            raise ValueError("out-of-order/replayed receipt or broken SHA chain")
        if close==prev_close+HOUR:
            if (item["event"]!="ONE_NEW_CONTIGUOUS_PROSPECTIVE_HOUR" or
                    item["segment_index"]!=previous["segment_index"]):
                raise ValueError("next contiguous hour must be genuinely new")
        elif (item["event"]!="HISTORICAL_72H_BOOTSTRAP" or
              item["segment_index"]!=previous["segment_index"]+1):
            raise ValueError("missed hours require NEW historical-only segment")
    historical=(item["event"]=="HISTORICAL_72H_BOOTSTRAP")
    expected_hours=BOOTSTRAP_HOURS if historical else 1
    batch=item["source_historical_batch"]
    if (not isinstance(batch,dict) or
            batch.get("kind")!="BOUNDED_HISTORICAL_MULTIASSET_DATA_GET_NOT_FORWARD_EVIDENCE" or
            batch.get("schema_version")!=1 or
            batch.get("asset_class")!="crypto" or
            batch.get("symbols")!=list(CRYPTO_SIX) or
            batch.get("feed")!="alpaca_crypto_us" or
            batch.get("adjustment")!="not_applicable" or
            batch.get("historical_not_independent_validation") is not True or
            batch.get("prospective_observations_verified")!=0 or
            batch.get("broker_order_submission")!="DISABLED" or
            batch.get("downloaded_utc")!=stamped.isoformat() or
            batch.get("start_utc")!=(close-expected_hours*HOUR).isoformat() or
            batch.get("end_utc")!=close.isoformat() or
            type(batch.get("page_count")) is not int or
            not 1<=batch["page_count"]<=40 or
            not isinstance(batch.get("bars"),dict) or
            set(batch["bars"])!=set(CRYPTO_SIX)):
        raise ValueError("raw source not the exact six-market closed-hour DATA batch")
    if _sha(batch)!=item["source_batch_sha256"]:
        raise ValueError("original raw provider batch SHA mismatch")
    reviews={}
    for symbol in CRYPTO_SIX:
        entries=batch["bars"][symbol]
        if not isinstance(entries,list) or len(entries)!=expected_hours:
            raise ValueError("incomplete per-asset bootstrap or prospective hour")
        bars=tuple(_raw_bar(x) for x in entries)
        if (bars[0].start_utc!=close-expected_hours*HOUR or
                bars[-1].closed_utc!=close or
                any(bar.feed!="alpaca_crypto_us" or
                    bar.captured_utc!=stamped for bar in bars)):
            raise ValueError("noncontiguous, mixed-feed, or nonfresh six-market source")
        validate_asset_dataset(bars,spec=candidate(symbol),as_of=stamped)
        # A first captured 72h is retrospective. The next confirmed candle
        # may be reclassified prospectively ONLY by this fresh chain audit.
        assessed=(bars if historical else (replace(bars[0],prospective=True),))
        review=validate_asset_dataset(
            assessed,spec=candidate(symbol),as_of=stamped)
        if review.prospective_bars!=(0 if historical else 1):
            raise ValueError("retrospective history misclassified as genuine observation")
        reviews[symbol]=review.content_sha256
    if (item["per_asset_observation_sha256"]!=reviews or
            item["prospective_asset_rows_in_this_receipt"]!=(0 if historical else 6) or
            item["distinct_prospective_hours_in_this_receipt"]!=(0 if historical else 1)):
        raise ValueError("per-symbol evidence SHA or independent clock-hour count differs")


def _audit_chain(root:Path) -> list[dict[str,object]]:
    folder=_receipt_folder(root)
    if not folder.exists():
        return []
    entries=tuple(folder.iterdir())
    if any(x.is_symlink() or not x.is_file() or not FILENAME.fullmatch(x.name) or
           x.stat().st_mode&0o077 or not 0<x.stat().st_size<=800_000 for x in entries):
        raise ValueError("unexpected, altered or insecure multi-market source receipt")
    records=[]
    for path in sorted(entries):
        receipt=json.loads(path.read_bytes())
        closed=_utc(datetime.fromisoformat(receipt["closed_hour_utc"]))
        if path.name!="hour-"+closed.strftime("%Y%m%dT%H%MZ")+".json":
            raise ValueError("immutable filename does not match original observed clock")
        _audit_one(receipt,records[-1] if records else None)
        records.append(receipt)
    return records


def universe_status(*,root:Path=ROOT) -> dict[str,object]:
    """Offline, credential-free full source chain verification; never calls provider."""
    base=_safe_root(Path(root))
    records=_audit_chain(base)
    segment=records[-1]["segment_index"] if records else 0
    current=[r for r in records if r["segment_index"]==segment]
    real=sum(r["distinct_prospective_hours_in_this_receipt"] for r in current)
    return {
        "kind":"SIX_CRYPTO_OFFLINE_PROSPECTIVE_SOURCE_CHAIN_STATUS",
        "status":"VERIFIED" if records else "NO_UNIVERSE_EVIDENCE_YET",
        "symbols":list(CRYPTO_SIX),
        "segment_index":segment,
        "latest_hour_utc":records[-1]["closed_hour_utc"] if records else None,
        "last_receipt_sha256":records[-1]["receipt_sha256"] if records else None,
        "all_segments_total_receipts":len(records),
        "current_segment_independent_prospective_hours":real,
        "current_segment_prospective_asset_bar_count":6*real,
        "historical_bootstrap_count":sum(
            r["event"]=="HISTORICAL_72H_BOOTSTRAP" for r in records),
        "ready_for_seven_day_audit":real>=168,
        "historical_baselines_count_as_prospective":False,
        "network_requests":"NONE",
        "credentials_accessed":"NONE",
        "broker_order_submission":"DISABLED",
    }


def _write_receipt(folder:Path,payload:dict[str,object]) -> Path:
    name="hour-"+datetime.fromisoformat(
        payload["closed_hour_utc"]).strftime("%Y%m%dT%H%MZ")+".json"
    target=folder/name
    if target.exists() or target.is_symlink():
        raise ValueError("new source receipt cannot overwrite a clock-hour")
    raw=(json.dumps(payload,sort_keys=True,indent=2)+"\n").encode("utf-8")
    flags=os.O_CREAT|os.O_EXCL|os.O_WRONLY
    if hasattr(os,"O_NOFOLLOW"):
        flags|=os.O_NOFOLLOW
    fd=os.open(target,flags,0o600)
    with os.fdopen(fd,"wb") as output:
        os.fchmod(output.fileno(),0o600)
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    dfd=os.open(folder,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)
    return target


def collect_six_crypto_once(
    *,root:Path,now:datetime,
    provider_factory:Callable[[],object],
) -> dict[str,object]:
    """One UTC HH:03..24 tick; validate full evidence chain BEFORE any GET.

    On a missed hour, create a NEW baseline only, never retrospectively
    label its bars as 6 newly prospective observations. Duplicate tick,
    outside-window, invalid volume or corrupted receipt makes ZERO GETs.
    """
    stamp=_utc(now)
    base=_safe_root(Path(root))
    with RuntimeFileLock(base/".six-crypto-source.lock"):
        records=_audit_chain(base)
        close=stamp.replace(minute=0,second=0,microsecond=0)
        if not 3<=stamp.minute<25:
            return {
                "status":"SAFE_SKIP_OUTSIDE_FRESH_CLOSED_HOUR_WINDOW",
                "network_requests":"NONE",
                "broker_order_submission":"DISABLED",
            }
        previous=records[-1] if records else None
        if previous is not None:
            old=_utc(datetime.fromisoformat(previous["closed_hour_utc"]))
            if close<=old:
                return {
                    "status":"SAFE_DUPLICATE_OR_CLOCK_ROLLBACK_NO_GET",
                    "network_requests":"NONE",
                    "last_verified_close_utc":old.isoformat(),
                    "broker_order_submission":"DISABLED",
                }
        bootstrap=previous is None or close>old+HOUR
        first=close- (BOOTSTRAP_HOURS if bootstrap else 1)*HOUR
        # Credential/provider loader is deliberately invoked only AFTER
        # complete old SHA chain, private volume, due time and duplicate gate.
        source=provider_factory()
        batch=source.fetch(
            specs=tuple(candidate(sym) for sym in CRYPTO_SIX),
            start=first,end=close,as_of=stamp)
        if not isinstance(batch,HistoricalDataBatch):
            raise ValueError("source did not return canonical historical DATA batch")
        expected_length=BOOTSTRAP_HOURS if bootstrap else 1
        if (tuple(batch.symbols)!=CRYPTO_SIX or
                set(batch.bars)!=set(CRYPTO_SIX) or
                any(not isinstance(batch.bars[sym],tuple) or
                    len(batch.bars[sym])!=expected_length
                    for sym in CRYPTO_SIX)):
            # Fail descriptively for sparse/missing provider bars BEFORE
            # accessing rows[0], writing receipt or marking prospectivity.
            raise ValueError("incomplete six-market returned source time window")
        event=("HISTORICAL_72H_BOOTSTRAP" if bootstrap else
               "ONE_NEW_CONTIGUOUS_PROSPECTIVE_HOUR")
        raw=batch.canonical()
        reviews={}
        for symbol in CRYPTO_SIX:
            rows=tuple(batch.bars[symbol])
            validated=(rows if bootstrap else (replace(rows[0],prospective=True),))
            reviews[symbol]=validate_asset_dataset(
                validated,spec=candidate(symbol),as_of=stamp).content_sha256
        new={
            "kind":"ISOLATED_SIX_CRYPTO_HOURLY_DATA_ONLY_RECEIPT",
            "schema_version":1,
            "event":event,
            "closed_hour_utc":close.isoformat(),
            "captured_utc":stamp.isoformat(),
            "segment_index":(1 if previous is None else
                 previous["segment_index"]+(1 if bootstrap else 0)),
            "previous_receipt_sha256":
                previous["receipt_sha256"] if previous else None,
            "source_batch_sha256":_sha(raw),
            "source_historical_batch":raw,
            "per_asset_observation_sha256":reviews,
            "prospective_asset_rows_in_this_receipt":0 if bootstrap else 6,
            "distinct_prospective_hours_in_this_receipt":0 if bootstrap else 1,
            "broker_order_submission":"DISABLED",
            "automatic_paper_trading":"DISABLED",
            "live_trading":"UNAVAILABLE",
        }
        new["receipt_sha256"]=_sha(new)
        _audit_one(new,previous)
        folder=_receipt_folder(base,create=True)
        _write_receipt(folder,new)
        return {
            "kind":"ISOLATED_SIX_CRYPTO_GET_ONLY_ONCE",
            "status":("HISTORICAL_BASELINE_ONLY_ZERO_PROSPECTIVE" if bootstrap
                      else "SIX_NEW_PROSPECTIVE_ASSET_BARS_ONE_CLOCK_HOUR"),
            "event":event,
            "closed_hour_utc":close.isoformat(),
            "segment_index":new["segment_index"],
            "recorded_prospective_asset_bars":new[
                "prospective_asset_rows_in_this_receipt"],
            "recorded_distinct_prospective_UTC_hours":new[
                "distinct_prospective_hours_in_this_receipt"],
            "source_SHA256":new["source_batch_sha256"],
            "receipt_SHA256":new["receipt_sha256"],
            "new_collector_uses_existing_BTC_forward_volume":False,
            "credential_values_in_output":False,
            "broker_order_submission":"DISABLED",
            "automatic_paper_trading":"DISABLED",
            "live_trading":"UNAVAILABLE",
        }

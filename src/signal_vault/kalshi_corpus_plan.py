"""Deterministic, outcome-direction-independent Kalshi historical corpus planning.

Reads the immutable Phase 38 public historical catalog, verifies its SHA
manifest, filters only structurally eligible settled binary markets, and picks
an exact bounded sample ordered by settlement timestamp and ticker. YES versus
NO outcome direction is never used for ordering or selection.

The plan performs no network access and submits no orders.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

MAX_FILE_BYTES=20_000_000
MAX_SAMPLE_SIZE=200
MIN_REQUIRED_LIFETIME_SECONDS=48*60*60
MAX_CAPTURE_WINDOW_SECONDS=120*24*60*60


def _read(path:Path)->tuple[dict[str,object],bytes]:
    if (
        path.is_symlink() or not path.is_file()
        or not 0<path.stat().st_size<=MAX_FILE_BYTES
    ):
        raise ValueError("Kalshi catalog file missing, unsafe, or oversized")
    raw=path.read_bytes()
    try:
        value=json.loads(raw)
    except (UnicodeDecodeError,json.JSONDecodeError) as exc:
        raise ValueError("Kalshi catalog file is not valid JSON") from exc
    if not isinstance(value,dict):
        raise ValueError("Kalshi catalog JSON must be an object")
    return value,raw


def _epoch(raw:object, *, name:str)->int:
    if not isinstance(raw,str) or not raw or len(raw)>64:
        raise ValueError(f"invalid Kalshi {name}")
    try:
        value=datetime.fromisoformat(raw.replace("Z","+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid Kalshi {name}") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"Kalshi {name} lacks timezone")
    return int(value.astimezone(timezone.utc).timestamp())


def _ticker(raw:object)->str:
    if (
        not isinstance(raw,str) or not raw or len(raw)>128
        or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in raw)
    ):
        raise ValueError("invalid Kalshi catalog market ticker")
    return raw


def plan_resolved_market_corpus(
    catalog_root:str|Path,
    *,
    sample_size:int=50,
)->dict[str,object]:
    if type(sample_size) is not int or not 1<=sample_size<=MAX_SAMPLE_SIZE:
        raise ValueError("bounded positive Kalshi corpus sample size required")
    root=Path(catalog_root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Kalshi catalog root must be a real directory")

    manifest,manifest_raw=_read(root/"manifest.json")
    if (
        manifest.get("kind")!="IMMUTABLE_KALSHI_PUBLIC_HISTORICAL_MARKET_CATALOG"
        or manifest.get("credentials_accessed")!="NONE"
        or manifest.get("broker_order_submission")!="DISABLED"
        or manifest.get("demo_order_submission")!="DISABLED"
        or manifest.get("live_trading")!="UNAVAILABLE"
    ):
        raise ValueError("invalid Kalshi historical catalog manifest")
    pages=manifest.get("market_pages")
    if not isinstance(pages,list) or not pages:
        raise ValueError("Kalshi historical catalog has no market pages")

    seen=set()
    eligible=[]
    total_markets=0
    for expected,page_receipt in enumerate(pages,1):
        if (
            not isinstance(page_receipt,Mapping)
            or page_receipt.get("page")!=expected
        ):
            raise ValueError("Kalshi catalog page receipt sequence invalid")
        path=root/f"markets-page-{expected:03d}.json"
        page,raw=_read(path)
        if hashlib.sha256(raw).hexdigest()!=page_receipt.get("sha256"):
            raise ValueError("Kalshi historical catalog page SHA mismatch")
        markets=page.get("markets")
        if not isinstance(markets,list):
            raise ValueError("Kalshi historical catalog page lacks markets")
        for market in markets:
            total_markets+=1
            if not isinstance(market,Mapping):
                raise ValueError("malformed Kalshi historical market")
            ticker=_ticker(market.get("ticker"))
            if ticker in seen:
                raise ValueError("duplicate Kalshi market across catalog pages")
            seen.add(ticker)

            # Structural eligibility only. The value yes/no is stored for later
            # scoring but does not influence sort order or selection.
            result=market.get("result")
            if result not in {"yes","no"}:
                continue
            if market.get("status") not in {"settled","closed"}:
                continue
            if market.get("mve_collection_ticker") not in (None,""):
                continue
            try:
                opened=_epoch(market.get("open_time"),name="open_time")
                settled=_epoch(market.get("settlement_ts"),name="settlement_ts")
            except ValueError:
                continue
            lifetime=settled-opened
            if not MIN_REQUIRED_LIFETIME_SECONDS<=lifetime<=MAX_CAPTURE_WINDOW_SECONDS:
                continue
            eligible.append({
                "ticker":ticker,
                "event_ticker":market.get("event_ticker"),
                "open_ts":opened,
                "settlement_ts":settled,
                "capture_start_ts":opened,
                "capture_end_ts":settled,
                "resolved_result_for_scoring_only":result,
            })

    if len(eligible)<sample_size:
        raise ValueError("historical catalog lacks requested eligible Kalshi sample")

    # Most recent exact sample; no outcome direction, price, volume, or
    # historical strategy result enters this ordering.
    ordered=sorted(
        eligible,
        key=lambda x:(x["settlement_ts"],x["ticker"]),
        reverse=True,
    )
    selected=ordered[:sample_size]
    return {
        "kind":"OFFLINE_DETERMINISTIC_KALSHI_RESOLVED_CORPUS_PLAN",
        "source_catalog_manifest_sha256":
            hashlib.sha256(manifest_raw).hexdigest(),
        "catalog_market_count":total_markets,
        "eligible_market_count":len(eligible),
        "selected_market_count":len(selected),
        "selection_rule":
            "MOST_RECENT_SETTLEMENT_THEN_TICKER_DESC_STRUCTURAL_FILTERS_ONLY",
        "selection_order_uses_outcome_direction":False,
        "selection_order_uses_historical_price_or_pnl":False,
        "minimum_market_lifetime_seconds":MIN_REQUIRED_LIFETIME_SECONDS,
        "maximum_capture_window_seconds":MAX_CAPTURE_WINDOW_SECONDS,
        "markets":selected,
        "credentials_accessed":"NONE",
        "network_requests":"NONE",
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }

"""Offline, no-lookahead scoring for one resolved Kalshi market evidence bundle.

This module validates the immutable Phase 51 evidence package, reads only
historical public market data, and scores historical YES trade-price closes
against the final binary settlement at fixed predeclared horizons. It does
not select a strategy, model fills, infer orderbook queue priority, or submit
orders.

The output is calibration evidence only. A low Brier error on one or many
historical markets is not itself authority to trade.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping, Sequence

DEFAULT_HORIZONS_SECONDS=(86400,21600,3600)
MAX_FILE_BYTES=20_000_000


def _read_json(path:Path)->tuple[dict[str,object],bytes]:
    if (
        path.is_symlink() or not path.is_file()
        or not 0<path.stat().st_size<=MAX_FILE_BYTES
    ):
        raise ValueError("Kalshi evidence file missing, unsafe, or oversized")
    raw=path.read_bytes()
    try:
        value=json.loads(raw)
    except (UnicodeDecodeError,json.JSONDecodeError) as exc:
        raise ValueError("Kalshi evidence file is not valid JSON") from exc
    if not isinstance(value,dict):
        raise ValueError("Kalshi evidence JSON must be an object")
    return value,raw


def _sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _settlement_epoch(raw:object)->int:
    if not isinstance(raw,str) or not raw or len(raw)>64:
        raise ValueError("invalid Kalshi settlement timestamp")
    try:
        dt=datetime.fromisoformat(raw.replace("Z","+00:00"))
    except ValueError as exc:
        raise ValueError("invalid Kalshi settlement timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("Kalshi settlement timestamp lacks timezone")
    return int(dt.astimezone(timezone.utc).timestamp())


def _probability(raw:object)->Decimal:
    if not isinstance(raw,str) or len(raw)>32:
        raise ValueError("Kalshi historical price must be a dollar string")
    try:
        value=Decimal(raw)
    except (InvalidOperation,ValueError) as exc:
        raise ValueError("invalid Kalshi historical price") from exc
    if not value.is_finite() or value<0 or value>1:
        raise ValueError("Kalshi YES probability must be within 0..1")
    return value


def _historical_close(candle:Mapping[str,object])->Decimal|None:
    price=candle.get("price")
    if not isinstance(price,Mapping):
        return None
    raw=price.get("close")
    if raw in (None,""):
        return None
    return _probability(raw)


def score_resolved_market_evidence(
    source_root:str|Path,
    *,
    horizons_seconds:Sequence[int]=DEFAULT_HORIZONS_SECONDS,
)->dict[str,object]:
    root=Path(source_root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Kalshi evidence root must be a real directory")

    manifest,manifest_raw=_read_json(root/"manifest.json")
    if (
        manifest.get("kind")!="IMMUTABLE_KALSHI_RESOLVED_MARKET_PUBLIC_EVIDENCE"
        or manifest.get("credentials_accessed")!="NONE"
        or manifest.get("demo_order_submission")!="DISABLED"
        or manifest.get("live_order_submission")!="DISABLED"
    ):
        raise ValueError("invalid Kalshi resolved evidence manifest")

    ticker=manifest.get("ticker")
    result=manifest.get("resolved_result")
    settlement_ts=manifest.get("settlement_ts")
    if not isinstance(ticker,str) or not ticker:
        raise ValueError("Kalshi evidence ticker missing")
    if result not in {"yes","no"}:
        raise ValueError("Kalshi evidence does not have binary resolved result")
    settled_at=_settlement_epoch(settlement_ts)

    metadata,metadata_raw=_read_json(root/"market.json")
    if hashlib.sha256(metadata_raw).hexdigest()!=manifest.get("market_metadata_sha256"):
        raise ValueError("Kalshi market metadata SHA mismatch")
    market=metadata.get("market")
    if not isinstance(market,Mapping):
        raise ValueError("Kalshi market metadata missing market object")
    if (
        market.get("ticker")!=ticker
        or market.get("result")!=result
        or market.get("settlement_ts")!=settlement_ts
    ):
        raise ValueError("Kalshi settlement metadata disagrees with manifest")

    candles,candle_raw=_read_json(root/"candlesticks.json")
    if hashlib.sha256(candle_raw).hexdigest()!=manifest.get("candlesticks_sha256"):
        raise ValueError("Kalshi candlestick SHA mismatch")
    if candles.get("ticker") not in (None,ticker):
        raise ValueError("Kalshi candlestick ticker mismatch")
    rows=candles.get("candlesticks")
    if not isinstance(rows,list) or not rows:
        raise ValueError("Kalshi evidence has no historical candlesticks")

    parsed=[]
    previous_ts=None
    for item in rows:
        if not isinstance(item,Mapping):
            raise ValueError("malformed Kalshi candlestick")
        at=item.get("end_period_ts")
        if type(at) is not int or at<0:
            raise ValueError("invalid Kalshi candlestick timestamp")
        if previous_ts is not None and at<=previous_ts:
            raise ValueError("Kalshi candlesticks must be strictly chronological")
        if at>settled_at:
            raise ValueError("post-settlement candle cannot enter historical scoring")
        close=_historical_close(item)
        if close is not None:
            parsed.append((at,close))
        previous_ts=at
    if not parsed:
        raise ValueError("Kalshi historical candles contain no trade-price closes")

    horizons=tuple(horizons_seconds)
    if (
        not horizons or len(horizons)>20
        or any(type(x) is not int or x<=0 for x in horizons)
        or len(set(horizons))!=len(horizons)
    ):
        raise ValueError("fixed positive unique Kalshi scoring horizons required")

    y=Decimal(1) if result=="yes" else Decimal(0)
    scores=[]
    for horizon in horizons:
        cutoff=settled_at-horizon
        eligible=[pair for pair in parsed if pair[0]<=cutoff]
        if not eligible:
            scores.append({
                "horizon_seconds_before_settlement":horizon,
                "observation_available":False,
                "yes_probability":None,
                "brier_error":None,
                "candle_end_ts":None,
            })
            continue
        at,p=eligible[-1]
        brier=(p-y)*(p-y)
        scores.append({
            "horizon_seconds_before_settlement":horizon,
            "observation_available":True,
            "yes_probability":str(p),
            "brier_error":str(brier),
            "candle_end_ts":at,
        })

    available=[x for x in scores if x["observation_available"]]
    mean_brier=(
        sum((Decimal(str(x["brier_error"])) for x in available),Decimal(0))
        / Decimal(len(available))
        if available else None
    )
    trade_pages=manifest.get("trade_pages")
    if not isinstance(trade_pages,list):
        raise ValueError("Kalshi trade-page manifest missing")
    for expected,item in enumerate(trade_pages,1):
        if not isinstance(item,Mapping) or item.get("page")!=expected:
            raise ValueError("Kalshi trade-page receipt sequence invalid")
        path=root/f"trades-page-{expected:03d}.json"
        if _sha(path)!=item.get("sha256"):
            raise ValueError("Kalshi trade-page SHA mismatch")

    return {
        "kind":"OFFLINE_KALSHI_RESOLVED_MARKET_CALIBRATION_SCORE",
        "ticker":ticker,
        "resolved_result":result,
        "settlement_ts":settlement_ts,
        "source_manifest_sha256":hashlib.sha256(manifest_raw).hexdigest(),
        "historical_trade_price_closes_verified":len(parsed),
        "fixed_horizon_scores":scores,
        "available_horizon_count":len(available),
        "mean_brier_error_over_available_fixed_horizons":
            None if mean_brier is None else str(mean_brier),
        "score_is_market_price_calibration_not_strategy_alpha":True,
        "historical_data_is_not_prospective_validation":True,
        "historical_orderbook_depth_reconstructed":False,
        "strategy_selection_performed":False,
        "automatic_strategy_promotion":"DISABLED",
        "credentials_accessed":"NONE",
        "network_requests":"NONE",
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }

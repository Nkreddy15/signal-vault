"""One-time historical feature warmup for the US-stock compact models.

This warmup exists only to avoid waiting 49 new market core hours before the
two-model stock shadow can calculate its first feature vector. It is never
counted as prospective validation evidence.

The warmup is fetched with the same strict Alpaca IEX DATA reader, ends at the
last full XNYS core hour before the current clean prospective segment, and is
stored under a reserved private child of the already-isolated stock namespace.
No account/broker endpoint or order method is available here.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime,timedelta,timezone
from decimal import Decimal,InvalidOperation
from pathlib import Path
from typing import Callable

from .ci_historical_equities import SYMBOLS
from .equity_session_grid import conservative_core_hour_plan
from .multi_asset_historical import BoundedAlpacaHistoricalBatch,HistoricalDataBatch
from .research_universe import ResearchBar,candidate,validate_asset_dataset

MODEL_WARMUP_CHILD="model-warmup"
TARGET_CORE_HOURS=60
MAX_WARMUP_FILE_BYTES=2_000_000


def _utc(value:datetime)->datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware warmup timestamp required")
    return value.astimezone(timezone.utc)


def _folder(stock_root:Path)->Path:
    root=Path(stock_root)
    if root.is_symlink() or not root.is_dir() or root.stat().st_mode&0o077:
        raise ValueError("stock root must be private real directory")
    folder=root/MODEL_WARMUP_CHILD
    if folder.exists() or folder.is_symlink():
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError("stock warmup child must be real directory")
    else:
        folder.mkdir(mode=0o700)
    os.chmod(folder,0o700)
    if folder.stat().st_mode&0o077:
        raise PermissionError("stock warmup child must be private")
    return folder


def _plan(first_forward_open:datetime,*,as_of:datetime):
    first=_utc(first_forward_open)
    checked=_utc(as_of)
    if first>=checked:
        raise ValueError("forward segment start must already be historical to bootstrap")
    plans=conservative_core_hour_plan(
        start_date=first.date()-timedelta(days=35),
        end_date_exclusive=first.date(),
        as_of=checked,
    )
    selected=[]
    hours=0
    for session in reversed(plans):
        selected.append(session)
        hours+=len(session.expected_opens)
        if hours>=TARGET_CORE_HOURS:
            break
    if hours<TARGET_CORE_HOURS:
        raise ValueError("not enough prior complete XNYS core hours for model warmup")
    selected=tuple(reversed(selected))
    if selected[-1].trading_date>=first.date().isoformat():
        raise AssertionError("warmup may not overlap forward session")
    return selected,hours


def collect_stock_model_warmup(
    *,
    stock_root:Path,
    first_forward_open:datetime,
    as_of:datetime,
    key:str,
    secret:str,
    provider_factory:Callable[...,BoundedAlpacaHistoricalBatch]=BoundedAlpacaHistoricalBatch,
)->dict[str,object]:
    if not isinstance(key,str) or not key.strip() or key!=key.strip():
        raise PermissionError("private DATA key required")
    if not isinstance(secret,str) or not secret.strip() or secret!=secret.strip():
        raise PermissionError("private DATA secret required")
    folder=_folder(stock_root)
    first=_utc(first_forward_open)
    target=folder/("stock-model-warmup-before-"+first.strftime("%Y%m%dT%H%MZ")+".json")
    if target.exists():
        record,datasets=load_stock_model_warmup(
            stock_root=stock_root,
            first_forward_open=first,
        )
        return {
            "kind":"PHASE162_STOCK_MODEL_FEATURE_WARMUP_GET_ONLY",
            "status":"ALREADY_AVAILABLE",
            "warmup_core_hours_per_asset":record["warmup_core_hours_per_asset"],
            "symbols":list(datasets),
            "network_requests":0,
            "broker_order_submission":"DISABLED",
        }

    plans,planned_hours=_plan(first,as_of=as_of)
    provider=provider_factory(key,secret)
    rows={symbol:[] for symbol in SYMBOLS}
    requests=0
    for session in plans:
        expected={symbol:session.expected_opens for symbol in SYMBOLS}
        batch=provider.fetch(
            specs=tuple(candidate(symbol) for symbol in SYMBOLS),
            start=session.query_start,
            end=session.query_end,
            as_of=_utc(as_of),
            equity_feed="iex",
            equity_expected_open_minutes=expected,
        )
        requests+=1
        if (
            not isinstance(batch,HistoricalDataBatch)
            or batch.asset_class!="us_equity"
            or batch.feed!="alpaca_equity_iex"
            or batch.adjustment!="all"
            or set(batch.bars)!=set(SYMBOLS)
        ):
            raise ValueError("warmup provider returned unexpected stock bundle")
        for symbol in SYMBOLS:
            source=tuple(batch.bars[symbol])
            review=validate_asset_dataset(
                source,
                spec=candidate(symbol),
                as_of=_utc(as_of),
                expected_session_opens_utc=expected[symbol],
            )
            if (
                review.feed!="alpaca_equity_iex|adjustment=all"
                or review.bar_count!=len(expected[symbol])
            ):
                raise ValueError("warmup stock IEX grid/provenance mismatch")
            rows[symbol].extend(source)

    if any(len(rows[symbol])!=planned_hours for symbol in SYMBOLS):
        raise ValueError("warmup stock symbol counts differ from plan")
    common=tuple(row.start_utc for row in rows[SYMBOLS[0]])
    if any(
        tuple(row.start_utc for row in rows[symbol])!=common
        for symbol in SYMBOLS
    ):
        raise ValueError("warmup stock symbols do not share exact core-hour grid")
    if common[-1]>=first:
        raise ValueError("historical warmup overlaps prospective segment")

    record={
        "kind":"PHASE162_STOCK_MODEL_FEATURE_WARMUP_GET_ONLY",
        "schema_version":1,
        "symbols":list(SYMBOLS),
        "feed":"alpaca_equity_iex",
        "adjustment":"all",
        "first_forward_open_utc":first.isoformat(),
        "selected_session_dates":[x.trading_date for x in plans],
        "warmup_core_hours_per_asset":planned_hours,
        "target_minimum_core_hours":TARGET_CORE_HOURS,
        "historical_rows_count_as_prospective":False,
        "bars":{
            symbol:[row.to_dict() for row in rows[symbol]]
            for symbol in SYMBOLS
        },
        "credential_values_in_record":False,
        "network_methods":["GET"],
        "broker_order_submission":"DISABLED",
        "paper_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
    canonical=json.dumps(record,sort_keys=True,separators=(",",":")).encode()
    record["payload_sha256"]=hashlib.sha256(canonical).hexdigest()
    raw=(json.dumps(record,sort_keys=True,separators=(",",":"))+"\n").encode()
    if len(raw)>MAX_WARMUP_FILE_BYTES:
        raise ValueError("warmup evidence unexpectedly exceeds bounded file size")
    flags=os.O_CREAT|os.O_EXCL|os.O_WRONLY
    if hasattr(os,"O_NOFOLLOW"):
        flags|=os.O_NOFOLLOW
    fd=os.open(target,flags,0o600)
    with os.fdopen(fd,"wb") as handle:
        os.fchmod(handle.fileno(),0o600)
        handle.write(raw);handle.flush();os.fsync(handle.fileno())
    return {
        "kind":"PHASE162_STOCK_MODEL_FEATURE_WARMUP_GET_ONLY",
        "status":"NEW_IMMUTABLE_WARMUP_CAPTURED",
        "warmup_core_hours_per_asset":planned_hours,
        "selected_session_count":len(plans),
        "network_requests":requests,
        "credentials_in_output":False,
        "broker_order_submission":"DISABLED",
    }


def load_stock_model_warmup(
    *,
    stock_root:Path,
    first_forward_open:datetime,
)->tuple[dict[str,object],dict[str,tuple[ResearchBar,...]]]:
    folder=_folder(stock_root)
    first=_utc(first_forward_open)
    target=folder/("stock-model-warmup-before-"+first.strftime("%Y%m%dT%H%MZ")+".json")
    if (
        target.is_symlink() or not target.is_file()
        or target.stat().st_mode&0o077
        or not 0<target.stat().st_size<=MAX_WARMUP_FILE_BYTES
    ):
        raise ValueError("stock model warmup file unavailable or unsafe")
    value=json.loads(target.read_text())
    if (
        not isinstance(value,dict)
        or value.get("kind")!="PHASE162_STOCK_MODEL_FEATURE_WARMUP_GET_ONLY"
        or value.get("schema_version")!=1
        or value.get("symbols")!=list(SYMBOLS)
        or value.get("feed")!="alpaca_equity_iex"
        or value.get("adjustment")!="all"
        or value.get("first_forward_open_utc")!=first.isoformat()
        or value.get("historical_rows_count_as_prospective") is not False
        or value.get("credential_values_in_record") is not False
        or value.get("network_methods")!=["GET"]
        or value.get("broker_order_submission")!="DISABLED"
        or value.get("paper_order_submission")!="DISABLED"
        or value.get("live_order_submission")!="DISABLED"
    ):
        raise ValueError("stock model warmup contract mismatch")
    digest=value.get("payload_sha256")
    unhashed=dict(value);unhashed.pop("payload_sha256",None)
    expected=hashlib.sha256(
        json.dumps(unhashed,sort_keys=True,separators=(",",":")).encode()
    ).hexdigest()
    if digest!=expected:
        raise ValueError("stock model warmup payload digest mismatch")

    rawbars=value.get("bars")
    if not isinstance(rawbars,dict) or set(rawbars)!=set(SYMBOLS):
        raise ValueError("stock warmup lacks exact six-symbol bars")
    datasets={}
    for symbol in SYMBOLS:
        items=rawbars[symbol]
        if not isinstance(items,list) or not items:
            raise ValueError("stock warmup symbol history missing")
        parsed=[]
        for obj in items:
            if not isinstance(obj,dict):
                raise ValueError("malformed stock warmup bar")
            try:
                bar=ResearchBar(
                    symbol=str(obj["symbol"]),
                    start_utc=datetime.fromisoformat(str(obj["start_utc"])),
                    open=Decimal(str(obj["open"])),
                    high=Decimal(str(obj["high"])),
                    low=Decimal(str(obj["low"])),
                    close=Decimal(str(obj["close"])),
                    volume=Decimal(str(obj["volume"])),
                    feed=str(obj["feed"]),
                    captured_utc=datetime.fromisoformat(str(obj["captured_utc"])),
                    prospective=bool(obj["prospective"]),
                )
            except (KeyError,ValueError,TypeError,InvalidOperation) as exc:
                raise ValueError("invalid stock warmup bar") from exc
            if (
                bar.symbol!=symbol
                or bar.prospective is not False
                or bar.feed!="alpaca_equity_iex|adjustment=all"
            ):
                raise ValueError("stock warmup bar provenance mismatch")
            parsed.append(bar)
        datasets[symbol]=tuple(parsed)
    grid=tuple(row.start_utc for row in datasets[SYMBOLS[0]])
    if any(tuple(row.start_utc for row in datasets[symbol])!=grid for symbol in SYMBOLS):
        raise ValueError("stock warmup grids differ by symbol")
    if len(grid)!=value.get("warmup_core_hours_per_asset"):
        raise ValueError("stock warmup count differs from record")
    if grid[-1]>=first:
        raise ValueError("stock warmup overlaps forward segment")
    return value,datasets

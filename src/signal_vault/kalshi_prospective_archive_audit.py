"""Offline integrity and completion audit for prospective Kalshi evidence.

Consumes one immutable precommitted plan, fixed-horizon quote snapshots, and
separate post-settlement outcome receipts. It never performs network access.

A market is valid only when BOTH frozen 24h and 6h decision snapshots were
captured prospectively and the settlement outcome was captured later. Missing
or invalid decision snapshots are never repaired from historical data.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping

from .kalshi_prospective_collector import (
    CAPTURE_WINDOW,
    HORIZONS,
    PLAN_KIND,
    SNAPSHOT_KIND,
    validate_prospective_kalshi_plan,
)
from .kalshi_prospective_settlement import SETTLEMENT_KIND

MAX_FILE_BYTES=2_000_000
MAX_FILES=500


def _read(path:Path)->tuple[dict[str,object],bytes]:
    if (
        path.is_symlink() or not path.is_file() or path.stat().st_mode&0o077
        or not 0<path.stat().st_size<=MAX_FILE_BYTES
    ):
        raise ValueError("unsafe prospective Kalshi evidence file")
    raw=path.read_bytes()
    try:
        value=json.loads(raw)
    except (UnicodeDecodeError,json.JSONDecodeError) as exc:
        raise ValueError("prospective Kalshi evidence is not valid JSON") from exc
    if not isinstance(value,dict):
        raise ValueError("prospective Kalshi evidence must be an object")
    canonical=(json.dumps(value,sort_keys=True,separators=(",",":"))+"\n").encode()
    if canonical!=raw:
        raise ValueError("prospective Kalshi evidence is noncanonical")
    return value,raw


def _utc(raw:object, *, name:str)->datetime:
    if not isinstance(raw,str) or not raw or len(raw)>64:
        raise ValueError(f"invalid Kalshi {name}")
    try:
        value=datetime.fromisoformat(raw.replace("Z","+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid Kalshi {name}") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"Kalshi {name} lacks timezone")
    return value.astimezone(timezone.utc)


def _price(raw:object, *, name:str)->str:
    if not isinstance(raw,str) or len(raw)>32:
        raise ValueError(f"Kalshi {name} must be a string")
    try:
        value=Decimal(raw)
    except (InvalidOperation,ValueError) as exc:
        raise ValueError(f"invalid Kalshi {name}") from exc
    if not value.is_finite() or value<0 or value>1:
        raise ValueError(f"Kalshi {name} outside 0..1")
    return str(value)


def _plan_file(root:Path)->tuple[dict[str,object],str]:
    matches=tuple(root.glob("kalshi-prospective-plan-*.json"))
    if len(matches)!=1:
        raise ValueError("prospective Kalshi archive requires exactly one plan")
    plan,raw=_read(matches[0])
    if plan.get("kind")!=PLAN_KIND:
        raise ValueError("unexpected prospective Kalshi plan kind")
    validate_prospective_kalshi_plan(plan)
    if not str(plan["plan_sha256"]).startswith(matches[0].stem.rsplit("-",1)[-1]):
        raise ValueError("prospective Kalshi plan filename digest mismatch")
    return plan,hashlib.sha256(raw).hexdigest()


def audit_kalshi_prospective_archive(root:str|Path)->dict[str,object]:
    folder=Path(root)
    if folder.is_symlink() or not folder.is_dir() or folder.stat().st_mode&0o077:
        raise ValueError("Kalshi prospective archive root must be private 0700")
    files=tuple(folder.iterdir())
    if not files or len(files)>MAX_FILES:
        raise ValueError("Kalshi prospective archive empty or exceeds file bound")

    plan,plan_file_sha=_plan_file(folder)
    markets=validate_prospective_kalshi_plan(plan)
    expected_names={
        next(folder.glob("kalshi-prospective-plan-*.json")).name,
    }
    records=[]
    valid_count=0
    missed_invalid=0
    pending=0
    valid_events=set()

    for item in markets:
        ticker=str(item["ticker"])
        event=str(item["event_ticker"])
        close=_utc(item["close_time"],name="planned close")
        snapshots={}
        invalid_reasons=[]
        for horizon in HORIZONS:
            name=f"kalshi-forward-{ticker}-{horizon}s.json"
            expected_names.add(name)
            path=folder/name
            if not path.exists():
                invalid_reasons.append(
                    f"MISSING_{horizon}_SECOND_FIXED_HORIZON_SNAPSHOT"
                )
                continue
            snap,_=_read(path)
            if (
                snap.get("kind")!=SNAPSHOT_KIND
                or snap.get("plan_sha256")!=plan["plan_sha256"]
                or snap.get("ticker")!=ticker
                or snap.get("event_ticker")!=event
                or snap.get("horizon_seconds_before_planned_close")!=horizon
                or snap.get("outcome_direction_recorded") is not False
                or snap.get("result_field_recorded") is not False
                or "result" in snap
                or snap.get("historical_backfill") is not False
                or snap.get("network_methods")!=["GET"]
                or snap.get("credentials_accessed")!="NONE"
                or snap.get("demo_order_submission")!="DISABLED"
                or snap.get("live_order_submission")!="DISABLED"
            ):
                raise ValueError("invalid Kalshi prospective snapshot contract")
            target=_utc(snap.get("target_capture_utc"),name="snapshot target")
            captured=_utc(snap.get("captured_at_utc"),name="snapshot capture")
            planned_close=_utc(
                snap.get("planned_close_time_utc"),name="snapshot planned close"
            )
            if (
                planned_close!=close
                or target!=close-timedelta(seconds=horizon)
                or not target<=captured<target+CAPTURE_WINDOW
            ):
                raise ValueError("Kalshi prospective snapshot clock mismatch")
            valid=snap.get("decision_valid")
            if type(valid) is not bool:
                raise ValueError("Kalshi snapshot validity must be boolean")
            if valid:
                bid=Decimal(_price(snap.get("yes_bid_dollars"),name="YES bid"))
                ask=Decimal(_price(snap.get("yes_ask_dollars"),name="YES ask"))
                last=Decimal(_price(snap.get("last_price_dollars"),name="last price"))
                if bid>ask:
                    raise ValueError("Kalshi prospective YES bid exceeds ask")
                snapshots[horizon]={
                    "target_capture_utc":target.isoformat(),
                    "captured_at_utc":captured.isoformat(),
                    "yes_bid_dollars":str(bid),
                    "yes_ask_dollars":str(ask),
                    "last_price_dollars":str(last),
                    "decision_valid":True,
                }
            else:
                if any(
                    snap.get(key) is not None
                    for key in ("yes_bid_dollars","yes_ask_dollars","last_price_dollars")
                ):
                    raise ValueError("invalid Kalshi decision snapshot leaked prices")
                invalid_reasons.append(
                    str(snap.get("invalid_reason") or "INVALID_DECISION_SNAPSHOT")
                )
                snapshots[horizon]={
                    "target_capture_utc":target.isoformat(),
                    "captured_at_utc":captured.isoformat(),
                    "decision_valid":False,
                }

        settlement_name=f"kalshi-settlement-{ticker}.json"
        expected_names.add(settlement_name)
        settlement_path=folder/settlement_name
        settlement=None
        if settlement_path.exists():
            receipt,_=_read(settlement_path)
            if (
                receipt.get("kind")!=SETTLEMENT_KIND
                or receipt.get("plan_sha256")!=plan["plan_sha256"]
                or receipt.get("ticker")!=ticker
                or receipt.get("event_ticker")!=event
                or receipt.get("public_status")!="settled"
                or receipt.get("resolved_result") not in {"yes","no"}
                or receipt.get("outcome_available_only_after_decision_stage") is not True
                or receipt.get("earlier_decision_snapshot_rewritten") is not False
                or receipt.get("post_settlement_decision_created") is not False
                or receipt.get("network_methods")!=["GET"]
                or receipt.get("credentials_accessed")!="NONE"
                or receipt.get("demo_order_submission")!="DISABLED"
                or receipt.get("live_order_submission")!="DISABLED"
            ):
                raise ValueError("invalid Kalshi prospective settlement contract")
            settlement_ts=_utc(receipt.get("settlement_ts"),name="settlement timestamp")
            settlement_capture=_utc(
                receipt.get("captured_at_utc"),name="settlement capture"
            )
            if settlement_ts>settlement_capture:
                raise ValueError("Kalshi settlement was captured before settlement")
            for snapshot in snapshots.values():
                if (
                    snapshot.get("decision_valid") is True
                    and _utc(snapshot["captured_at_utc"],name="decision capture")
                    >= settlement_ts
                ):
                    raise ValueError("Kalshi decision evidence was captured after settlement")
            settlement={
                "resolved_result":receipt["resolved_result"],
                "settlement_ts":settlement_ts.isoformat(),
                "captured_at_utc":settlement_capture.isoformat(),
            }

        all_decisions=all(
            horizon in snapshots and snapshots[horizon].get("decision_valid") is True
            for horizon in HORIZONS
        )
        if all_decisions and settlement is not None:
            status="VALID_COMPLETE"
            valid_count+=1
            valid_events.add(event)
        elif settlement is None and not invalid_reasons:
            status="PENDING_SETTLEMENT_OR_DECISION"
            pending+=1
        else:
            status="MISSED_OR_INVALID"
            missed_invalid+=1
        records.append({
            "ticker":ticker,
            "event_ticker":event,
            "planned_close_time_utc":close.isoformat(),
            "status":status,
            "invalid_reasons":invalid_reasons,
            "snapshots":snapshots,
            "settlement":settlement,
        })

    unexpected={p.name for p in files}-expected_names
    if unexpected:
        raise ValueError("unexpected file in prospective Kalshi archive")

    planned=len(markets)
    if valid_count+missed_invalid+pending!=planned:
        raise AssertionError("Kalshi prospective completion accounting mismatch")
    return {
        "kind":"KALSHI_PROSPECTIVE_ARCHIVE_AUDIT_NO_ORDERS",
        "plan_sha256":plan["plan_sha256"],
        "plan_file_sha256":plan_file_sha,
        "hypothesis_policy_version":plan["hypothesis_policy_version"],
        "planned_market_count":planned,
        "valid_prospective_market_count":valid_count,
        "missed_or_invalid_market_count":missed_invalid,
        "pending_market_count":pending,
        "distinct_valid_event_count":len(valid_events),
        "capture_coverage_fraction":str(
            Decimal(valid_count)/Decimal(planned)
        ),
        "markets":records,
        "outcome_direction_used_for_market_selection":False,
        "historical_backfill_count":0,
        "post_settlement_decision_count":0,
        "source_integrity_passed":True,
        "network_requests":"NONE",
        "credentials_accessed":"NONE",
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }

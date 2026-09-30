"""Offline audit of prospective US-equity forward evidence.

The auditor consumes only immutable premarket session plans and per-core-hour
receipts produced by equity_forward_collector. It performs no network access,
uses no credentials, and never submits orders.

A missed planned hour or a missing precommitted XNYS session breaks the current
prospective segment. Later complete sessions may start a new segment, but older
gaps are never hidden or backfilled.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping

from .ci_historical_equities import SYMBOLS
from .equity_forward_collector import (
    PLAN_KIND,
    PLAN_VERSION,
    RECEIPT_KIND,
    _validate_plan,
)

PLAN_RE = re.compile(
    r"equity-forward-plan-(\d{8})-([0-9a-f]{16})\.json\Z"
)
RECEIPT_RE = re.compile(
    r"equity-forward-(\d{8}T\d{4}Z)-([0-9a-f]{16})\.json\Z"
)
MAX_FILES = 2000
MAX_FILE_BYTES = 2_000_000
HOUR = timedelta(hours=1)


def _read_json(path: Path) -> tuple[dict[str, object], bytes]:
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_mode & 0o077
        or not 0 < path.stat().st_size <= MAX_FILE_BYTES
    ):
        raise ValueError("unsafe or oversized equity forward evidence file")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid equity forward JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("equity forward evidence must be an object")
    canonical = (
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    if canonical != raw:
        raise ValueError("equity forward evidence is not canonical")
    return value, raw


def _stamp(raw: object) -> datetime:
    if not isinstance(raw, str) or len(raw) > 64:
        raise ValueError("invalid equity forward timestamp")
    value = datetime.fromisoformat(raw)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("equity forward timestamp missing timezone")
    return value.astimezone(timezone.utc)


def _xnys_sessions_between(
    start_date: date,
    end_date_inclusive: date,
) -> tuple[date, ...]:
    if start_date > end_date_inclusive:
        raise ValueError("invalid XNYS audit date range")
    try:
        import exchange_calendars as xc
    except ImportError as exc:
        raise RuntimeError(
            "equity forward audit requires optional [equity-research]"
        ) from exc
    calendar = xc.get_calendar(
        "XNYS",
        start=start_date.isoformat(),
        end=(end_date_inclusive + timedelta(days=1)).isoformat(),
    )
    return tuple(
        session.date()
        for session in calendar.sessions
        if start_date <= session.date() <= end_date_inclusive
    )


def _validate_receipt(
    receipt: Mapping[str, object],
    *,
    expected_file_digest_prefix: str,
    raw: bytes,
) -> tuple[str, datetime]:
    if (
        receipt.get("kind") != RECEIPT_KIND
        or receipt.get("schema_version") != 1
        or receipt.get("policy_version") != PLAN_VERSION
        or receipt.get("symbols") != list(SYMBOLS)
        or receipt.get("feed") != "alpaca_equity_iex"
        or receipt.get("adjustment") != "all"
        or receipt.get("prospective_core_hours_per_asset_added") != 1
        or receipt.get("prospective_asset_bar_count_added") != len(SYMBOLS)
        or receipt.get("complete_six_stock_grid_verified") is not True
        or receipt.get("historical_backfill_count") != 0
        or receipt.get("hidden_gap_or_interpolation_count") != 0
        or receipt.get("network_methods") != ["GET"]
        or receipt.get("credentials_in_receipt") is not False
        or receipt.get("broker_order_submission") != "DISABLED"
        or receipt.get("paper_order_submission") != "DISABLED"
        or receipt.get("live_order_submission") != "DISABLED"
        or receipt.get("live_trading") != "UNAVAILABLE"
    ):
        raise ValueError("invalid equity forward receipt contract")
    if hashlib.sha256(raw).hexdigest()[:16] != expected_file_digest_prefix:
        raise ValueError("equity forward receipt filename digest mismatch")

    plan_sha = receipt.get("plan_sha256")
    if not isinstance(plan_sha, str) or len(plan_sha) != 64:
        raise ValueError("equity forward receipt lacks plan digest")
    core_open = _stamp(receipt.get("core_open_utc"))
    core_close = _stamp(receipt.get("core_close_utc"))
    captured = _stamp(receipt.get("captured_at_utc"))
    if core_open + HOUR != core_close:
        raise ValueError("equity forward receipt core-hour bounds mismatch")
    if not core_close < captured < core_close + HOUR:
        raise ValueError("equity forward receipt capture time is implausible")
    planned = _stamp(receipt.get("session_plan_planned_at_utc"))
    exchange_open = _stamp(receipt.get("session_plan_exchange_open_utc"))
    if planned >= exchange_open:
        raise ValueError("equity session plan was not precommitted before open")
    expected_opens_raw = receipt.get("session_plan_expected_core_opens_utc")
    if (
        not isinstance(expected_opens_raw, list)
        or receipt.get("session_plan_expected_core_hour_count")
        != len(expected_opens_raw)
    ):
        raise ValueError("equity receipt lacks complete session-plan grid")
    expected_opens = tuple(_stamp(x) for x in expected_opens_raw)
    if core_open not in expected_opens:
        raise ValueError("equity receipt hour not in its archived session plan")

    bars = receipt.get("bars")
    if not isinstance(bars, Mapping) or set(bars) != set(SYMBOLS):
        raise ValueError("equity forward receipt lacks exact six-stock bars")
    canonical_bars: dict[str, object] = {}
    for symbol in SYMBOLS:
        obj = bars[symbol]
        if not isinstance(obj, Mapping):
            raise ValueError("malformed equity forward bar")
        if (
            obj.get("symbol") != symbol
            or _stamp(obj.get("start_utc")) != core_open
            or _stamp(obj.get("closed_utc")) != core_close
            or _stamp(obj.get("captured_utc")) != captured
            or obj.get("feed") != "alpaca_equity_iex|adjustment=all"
            or obj.get("prospective") is not True
        ):
            raise ValueError("equity forward bar provenance mismatch")
        canonical_bars[symbol] = dict(obj)
    digest = hashlib.sha256(
        json.dumps(canonical_bars, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if receipt.get("bar_evidence_sha256") != digest:
        raise ValueError("equity forward bar evidence digest mismatch")
    return plan_sha, core_open


def audit_equity_forward_archive(root: str | Path) -> dict[str, object]:
    folder = Path(root)
    if (
        folder.is_symlink()
        or not folder.is_dir()
        or folder.stat().st_mode & 0o077
    ):
        raise ValueError("equity forward archive root must be private 0700")
    items = tuple(sorted(folder.iterdir(), key=lambda p: p.name))
    if not items or len(items) > MAX_FILES:
        raise ValueError("equity forward archive is empty or exceeds file bound")

    plans_by_date: dict[date, dict[str, object]] = {}
    plans_by_sha: dict[str, dict[str, object]] = {}
    receipts_by_plan: dict[str, dict[datetime, dict[str, object]]] = {}
    receipt_count = 0

    for path in items:
        plan_match = PLAN_RE.fullmatch(path.name)
        receipt_match = RECEIPT_RE.fullmatch(path.name)
        if plan_match:
            plan, raw = _read_json(path)
            _validate_plan(plan)
            if plan.get("kind") != PLAN_KIND:
                raise ValueError("unexpected equity session-plan kind")
            trading_date = date.fromisoformat(str(plan["trading_date"]))
            if trading_date.strftime("%Y%m%d") != plan_match.group(1):
                raise ValueError("equity plan filename date mismatch")
            plan_sha = str(plan["plan_sha256"])
            if not plan_sha.startswith(plan_match.group(2)):
                raise ValueError("equity plan filename digest mismatch")
            if trading_date in plans_by_date or plan_sha in plans_by_sha:
                raise ValueError("duplicate equity forward session plan")
            plans_by_date[trading_date] = plan
            plans_by_sha[plan_sha] = plan
            receipts_by_plan.setdefault(plan_sha, {})
            continue
        if receipt_match:
            receipt, raw = _read_json(path)
            plan_sha, core_open = _validate_receipt(
                receipt,
                expected_file_digest_prefix=receipt_match.group(2),
                raw=raw,
            )
            if core_open.strftime("%Y%m%dT%H%MZ") != receipt_match.group(1):
                raise ValueError("equity receipt filename timestamp mismatch")
            per_plan = receipts_by_plan.setdefault(plan_sha, {})
            if core_open in per_plan:
                raise ValueError("duplicate prospective equity core hour")
            per_plan[core_open] = receipt
            receipt_count += 1
            continue
        raise ValueError("unexpected file in equity forward evidence root")

    if not plans_by_date:
        raise ValueError("equity forward archive has no precommitted session plans")
    if any(plan_sha not in plans_by_sha for plan_sha in receipts_by_plan):
        raise ValueError("equity receipt references missing session plan")

    first_date = min(plans_by_date)
    last_date = max(plans_by_date)
    expected_sessions = _xnys_sessions_between(first_date, last_date)
    statuses = []
    gap_count = 0
    for session_date in expected_sessions:
        plan = plans_by_date.get(session_date)
        if plan is None:
            statuses.append({
                "trading_date": session_date.isoformat(),
                "status": "MISSING_PRECOMMITTED_SESSION_PLAN",
                "expected_core_hours": 0,
                "observed_core_hours": 0,
                "missing_core_hours": [],
            })
            gap_count += 1
            continue
        plan_sha = str(plan["plan_sha256"])
        expected = tuple(
            _stamp(x) for x in plan["expected_core_opens_utc"]  # type: ignore[index]
        )
        observed_map = receipts_by_plan.get(plan_sha, {})
        observed = tuple(sorted(observed_map))
        missing = tuple(x for x in expected if x not in observed_map)
        extra = tuple(x for x in observed if x not in expected)
        if extra:
            raise ValueError("equity archive contains receipt outside session plan")
        complete = not missing and observed == expected
        if not complete:
            gap_count += len(missing) if missing else 1
        statuses.append({
            "trading_date": session_date.isoformat(),
            "status": "COMPLETE" if complete else "INCOMPLETE",
            "expected_core_hours": len(expected),
            "observed_core_hours": len(observed),
            "missing_core_hours": [x.isoformat() for x in missing],
            "plan_sha256": plan_sha,
        })

    last_bad = -1
    for idx, item in enumerate(statuses):
        if item["status"] != "COMPLETE":
            last_bad = idx
    segment_statuses = statuses[last_bad + 1 :]
    if any(x["status"] != "COMPLETE" for x in segment_statuses):
        raise AssertionError("current equity segment construction failed")
    segment_sessions = len(segment_statuses)
    segment_hours = sum(int(x["observed_core_hours"]) for x in segment_statuses)

    return {
        "kind": "EQUITY_FORWARD_ARCHIVE_AUDIT_NO_ORDERS",
        "policy_version": PLAN_VERSION,
        "symbols": list(SYMBOLS),
        "archive_session_plan_count": len(plans_by_date),
        "archive_prospective_receipt_count": receipt_count,
        "audited_xnys_sessions": statuses,
        "prior_or_current_gap_count": gap_count,
        "current_segment_distinct_xnys_sessions": segment_sessions,
        "current_segment_prospective_core_hours_per_asset": segment_hours,
        "current_segment_prospective_asset_bar_count": segment_hours * len(SYMBOLS),
        "current_segment_complete_six_stock_grid_verified": bool(segment_statuses),
        "current_segment_hidden_gap_or_interpolation_count": 0,
        "historical_backfill_count": 0,
        "source_integrity_passed": True,
        "network_requests": "NONE",
        "credentials_accessed": "NONE",
        "broker_order_submission": "DISABLED",
        "paper_order_submission": "DISABLED",
        "live_order_submission": "DISABLED",
        "live_trading": "UNAVAILABLE",
    }

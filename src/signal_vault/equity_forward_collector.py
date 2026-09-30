"""Prospective GET-only US-equity core-hour collector.

This module creates a precommitted XNYS session plan before the session opens,
then permits exactly one six-stock IEX data capture for each planned full core
hour during a narrow post-close window. Missing windows are missed forever:
there is no historical backfill path.

The collector uses the existing strict Alpaca DATA host reader. It never imports
broker/account/order modules, never uses POST, and never enables PAPER or LIVE
execution.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from .ci_historical_equities import SYMBOLS
from .multi_asset_historical import (
    BoundedAlpacaHistoricalBatch,
    HistoricalDataBatch,
)
from .research_universe import ResearchBar, candidate, validate_asset_dataset

PLAN_KIND = "PRECOMMITTED_XNYS_SIX_STOCK_FORWARD_SESSION_PLAN"
PLAN_VERSION = "equity-forward-session-v1-predeclared-20260930"
RECEIPT_KIND = "PROSPECTIVE_XNYS_SIX_STOCK_CORE_HOUR_GET_ONLY"
CAPTURE_EARLIEST_AFTER_CLOSE = timedelta(minutes=3)
CAPTURE_LATEST_AFTER_CLOSE = timedelta(minutes=30)
HOUR = timedelta(hours=1)


def _utc(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("timezone-aware timestamp required")
    return value.astimezone(timezone.utc)


def _stamp(raw: object) -> datetime:
    if not isinstance(raw, str) or len(raw) > 64:
        raise ValueError("invalid stored timestamp")
    return _utc(datetime.fromisoformat(raw))


def _session_core_opens(
    trading_date: date,
) -> tuple[datetime, datetime, tuple[datetime, ...], bool, str]:
    if type(trading_date) is not date:
        raise ValueError("date-only XNYS trading date required")
    try:
        import exchange_calendars as xc
    except ImportError as exc:
        raise RuntimeError(
            "equity forward planning requires optional [equity-research]"
        ) from exc
    try:
        calendar = xc.get_calendar(
            "XNYS",
            start=trading_date.isoformat(),
            end=(trading_date + timedelta(days=1)).isoformat(),
        )
        matches = tuple(
            session
            for session in calendar.sessions
            if session.date() == trading_date
        )
    except Exception as exc:
        raise ValueError("unable to resolve XNYS trading date") from exc
    if len(matches) != 1:
        raise ValueError("requested date is not exactly one XNYS trading session")
    session = matches[0]
    opened = calendar.session_open(session).to_pydatetime().astimezone(timezone.utc)
    closed = calendar.session_close(session).to_pydatetime().astimezone(timezone.utc)
    first = opened.replace(minute=0, second=0, microsecond=0)
    if first < opened:
        first += HOUR
    final = closed.replace(minute=0, second=0, microsecond=0)
    if final > closed:
        final -= HOUR
    opens: list[datetime] = []
    cursor = first
    while cursor + HOUR <= final:
        opens.append(cursor)
        cursor += HOUR
    if not opens:
        raise ValueError("XNYS session has no complete core clock hours")
    return (
        opened,
        closed,
        tuple(opens),
        session in set(calendar.early_closes),
        xc.__version__,
    )


def precommit_equity_forward_session(
    *,
    trading_date: date,
    planned_at: datetime,
) -> dict[str, object]:
    planned = _utc(planned_at)
    opened, closed, core_opens, early_close, calendar_version = _session_core_opens(
        trading_date
    )
    if planned >= opened:
        raise ValueError("forward equity session must be precommitted before XNYS opens")
    payload = {
        "kind": PLAN_KIND,
        "policy_version": PLAN_VERSION,
        "trading_date": trading_date.isoformat(),
        "planned_at_utc": planned.isoformat(),
        "exchange_open_utc": opened.isoformat(),
        "exchange_close_utc": closed.isoformat(),
        "expected_core_opens_utc": [x.isoformat() for x in core_opens],
        "expected_core_hour_count": len(core_opens),
        "symbols": list(SYMBOLS),
        "feed": "iex",
        "adjustment": "all",
        "market_calendar": "XNYS",
        "exchange_calendar_package_version": calendar_version,
        "session_is_early_close": early_close,
        "historical_backfill_allowed": False,
        "network_requests": "NONE",
        "credentials_accessed": "NONE",
        "broker_order_submission": "DISABLED",
        "live_order_submission": "DISABLED",
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {**payload, "plan_sha256": hashlib.sha256(raw).hexdigest()}


def _validate_plan(plan: dict[str, object]) -> tuple[date, tuple[datetime, ...], str]:
    if (
        not isinstance(plan, dict)
        or plan.get("kind") != PLAN_KIND
        or plan.get("policy_version") != PLAN_VERSION
        or plan.get("symbols") != list(SYMBOLS)
        or plan.get("feed") != "iex"
        or plan.get("adjustment") != "all"
        or plan.get("market_calendar") != "XNYS"
        or plan.get("historical_backfill_allowed") is not False
        or plan.get("broker_order_submission") != "DISABLED"
        or plan.get("live_order_submission") != "DISABLED"
    ):
        raise ValueError("invalid precommitted equity forward plan")
    raw_hash = plan.get("plan_sha256")
    if not isinstance(raw_hash, str) or len(raw_hash) != 64:
        raise ValueError("missing equity plan digest")
    unhashed = dict(plan)
    unhashed.pop("plan_sha256", None)
    expected = hashlib.sha256(
        json.dumps(unhashed, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if expected != raw_hash:
        raise ValueError("equity forward plan digest mismatch")
    trading_date = date.fromisoformat(str(plan["trading_date"]))
    opens_raw = plan.get("expected_core_opens_utc")
    if not isinstance(opens_raw, list) or not opens_raw:
        raise ValueError("equity plan lacks core-hour schedule")
    opens = tuple(_stamp(x) for x in opens_raw)
    if opens != tuple(sorted(set(opens))):
        raise ValueError("equity plan core-hour schedule must be sorted and unique")
    planned = _stamp(plan["planned_at_utc"])
    exchange_open = _stamp(plan["exchange_open_utc"])
    if planned >= exchange_open:
        raise ValueError("equity plan was not committed before market open")
    if plan.get("expected_core_hour_count") != len(opens):
        raise ValueError("equity plan core-hour count mismatch")
    return trading_date, opens, raw_hash


@dataclass(frozen=True)
class ProspectiveEquityHour:
    receipt: dict[str, object]
    bars: dict[str, tuple[ResearchBar, ...]]

    def canonical_bytes(self) -> bytes:
        return (
            json.dumps(self.receipt, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")


def collect_precommitted_equity_hour(
    *,
    plan: dict[str, object],
    core_open_utc: datetime,
    captured_at: datetime,
    key: str,
    secret: str,
    provider_factory: Callable[..., BoundedAlpacaHistoricalBatch] = (
        BoundedAlpacaHistoricalBatch
    ),
) -> ProspectiveEquityHour:
    trading_date, planned_opens, plan_sha = _validate_plan(plan)
    core_open = _utc(core_open_utc)
    captured = _utc(captured_at)
    if core_open not in planned_opens:
        raise ValueError("requested stock hour was not in precommitted XNYS plan")
    if core_open.date() != trading_date:
        raise ValueError("stock core hour does not belong to planned trading date")
    closed = core_open + HOUR
    if not (
        closed + CAPTURE_EARLIEST_AFTER_CLOSE
        <= captured
        < closed + CAPTURE_LATEST_AFTER_CLOSE
    ):
        raise ValueError("missed or premature equity prospective capture window")
    if not isinstance(key, str) or not key.strip() or key != key.strip():
        raise PermissionError("dedicated PAPER DATA key required")
    if not isinstance(secret, str) or not secret.strip() or secret != secret.strip():
        raise PermissionError("dedicated PAPER DATA secret required")

    expected = {symbol: (core_open,) for symbol in SYMBOLS}
    provider = provider_factory(key, secret)
    batch = provider.fetch(
        specs=tuple(candidate(symbol) for symbol in SYMBOLS),
        start=core_open,
        end=closed,
        as_of=captured,
        equity_feed="iex",
        equity_expected_open_minutes=expected,
    )
    if (
        not isinstance(batch, HistoricalDataBatch)
        or batch.asset_class != "us_equity"
        or batch.symbols != tuple(SYMBOLS)
        or batch.feed != "alpaca_equity_iex"
        or batch.adjustment != "all"
        or set(batch.bars) != set(SYMBOLS)
    ):
        raise ValueError("provider did not return exact six-stock IEX batch")

    rebuilt: dict[str, tuple[ResearchBar, ...]] = {}
    bar_receipts: dict[str, dict[str, str | bool]] = {}
    for symbol in SYMBOLS:
        rows = tuple(batch.bars[symbol])
        if len(rows) != 1 or rows[0].start_utc != core_open:
            raise ValueError("prospective stock batch must contain exactly one planned bar")
        source = rows[0]
        bar = ResearchBar(
            symbol=symbol,
            start_utc=source.start_utc,
            open=source.open,
            high=source.high,
            low=source.low,
            close=source.close,
            volume=source.volume,
            feed=source.feed,
            captured_utc=captured,
            prospective=True,
        )
        validate_asset_dataset(
            (bar,),
            spec=candidate(symbol),
            as_of=captured,
            expected_session_opens_utc=(core_open,),
        )
        rebuilt[symbol] = (bar,)
        bar_receipts[symbol] = bar.to_dict()

    evidence_raw = json.dumps(
        bar_receipts, sort_keys=True, separators=(",", ":")
    ).encode()
    receipt = {
        "kind": RECEIPT_KIND,
        "schema_version": 1,
        "policy_version": PLAN_VERSION,
        "plan_sha256": plan_sha,
        "trading_date": trading_date.isoformat(),
        "session_plan_planned_at_utc": str(plan["planned_at_utc"]),
        "session_plan_exchange_open_utc": str(plan["exchange_open_utc"]),
        "session_plan_exchange_close_utc": str(plan["exchange_close_utc"]),
        "session_plan_expected_core_opens_utc": list(plan["expected_core_opens_utc"]),
        "session_plan_expected_core_hour_count": int(plan["expected_core_hour_count"]),
        "core_open_utc": core_open.isoformat(),
        "core_close_utc": closed.isoformat(),
        "captured_at_utc": captured.isoformat(),
        "symbols": list(SYMBOLS),
        "feed": "alpaca_equity_iex",
        "adjustment": "all",
        "prospective_core_hours_per_asset_added": 1,
        "prospective_asset_bar_count_added": len(SYMBOLS),
        "complete_six_stock_grid_verified": True,
        "historical_backfill_count": 0,
        "hidden_gap_or_interpolation_count": 0,
        "bar_evidence_sha256": hashlib.sha256(evidence_raw).hexdigest(),
        "bars": bar_receipts,
        "network_methods": ["GET"],
        "credentials_in_receipt": False,
        "broker_order_submission": "DISABLED",
        "paper_order_submission": "DISABLED",
        "live_order_submission": "DISABLED",
        "live_trading": "UNAVAILABLE",
    }
    return ProspectiveEquityHour(receipt=receipt, bars=rebuilt)


def archive_prospective_equity_hour(
    item: ProspectiveEquityHour,
    *,
    output_root: str | Path,
) -> Path:
    if not isinstance(item, ProspectiveEquityHour):
        raise ValueError("prospective stock receipt required")
    root = Path(output_root)
    if (
        root.is_symlink()
        or not root.is_dir()
        or root.stat().st_mode & 0o077
    ):
        raise ValueError("equity forward root must preexist as private 0700 directory")
    if root.resolve() == Path("/var/lib/signal-vault/forward"):
        raise ValueError("stock forward evidence must not share the BTC evidence root")
    raw = item.canonical_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    opened = _stamp(item.receipt["core_open_utc"])
    name = f"equity-forward-{opened.strftime('%Y%m%dT%H%MZ')}-{digest[:16]}.json"
    path = root / name
    if path.exists() or path.is_symlink():
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_mode & 0o077
            or path.read_bytes() != raw
        ):
            raise ValueError("immutable equity forward evidence collision")
        return path
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return path

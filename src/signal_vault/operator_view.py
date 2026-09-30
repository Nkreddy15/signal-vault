"""Restricted, observational view over the local PAPER-only ledger.

This module NEVER creates/migrates a database, changes controls, calls a broker,
or executes orders. It intentionally does not expose raw provider payloads,
order identifiers, account identifiers or event JSON.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import json
import re
import sqlite3
import stat


class OperatorSnapshotError(ValueError):
    """Invalid, missing or inconsistent local paper ledger. Fail closed."""


def _number(value: object, *, nonnegative: bool = True) -> str:
    if not isinstance(value, str):
        raise OperatorSnapshotError("invalid ledger amount representation")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise OperatorSnapshotError("invalid ledger amount") from exc
    if not number.is_finite() or (nonnegative and number < 0):
        raise OperatorSnapshotError("non-finite or negative ledger amount")
    return str(number)


def _timestamp(value: object) -> str:
    if not isinstance(value, str):
        raise OperatorSnapshotError("invalid ledger event time")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise OperatorSnapshotError("invalid ledger event time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OperatorSnapshotError("unqualified ledger event time")
    return parsed.astimezone(timezone.utc).isoformat()


def _event_name(value: object) -> str:
    return value if isinstance(value, str) and re.fullmatch(r"[A-Z][A-Z_0-9]{0,63}", value) else "UNRECOGNIZED_EVENT"


_MM_LANES = ("crypto", "us_equity", "kalshi_event_contract")
_MM_STAGES = {
    "draft_approved", "submission_pending", "unknown_result",
    "broker_accepted", "partially_filled",
    "broker_terminal_unreconciled", "reconciled",
}


def _multimarket_execution_snapshot(
    con: sqlite3.Connection,
    *,
    max_items: int,
) -> dict[str, object]:
    """Sanitized read-only view of the optional shared cross-market journal."""
    present = {
        row[0]
        for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('mm_execution_drafts','mm_execution_states')"
        )
    }
    if not present:
        return {
            "available": False,
            "count": 0,
            "unresolved": 0,
            "by_lane": {lane: {"count": 0, "unresolved": 0} for lane in _MM_LANES},
            "recent": [],
        }
    if present != {"mm_execution_drafts", "mm_execution_states"}:
        raise OperatorSnapshotError("incomplete multi-market execution journal schema")

    joined = tuple(con.execute(
        """SELECT d.market_lane,d.instrument,s.state_json,s.updated_utc
           FROM mm_execution_states s
           JOIN mm_execution_drafts d USING(client_order_id)
           ORDER BY s.updated_utc DESC"""
    ))
    by_lane = {lane: {"count": 0, "unresolved": 0} for lane in _MM_LANES}
    recent = []
    unresolved = 0
    for index, row in enumerate(joined):
        lane, instrument, raw_state, updated = row
        if lane not in by_lane:
            raise OperatorSnapshotError("unknown multi-market execution lane")
        if (
            not isinstance(instrument, str)
            or not instrument.strip()
            or len(instrument) > 160
            or any(ch in instrument for ch in "\r\n\x00")
        ):
            raise OperatorSnapshotError("invalid multi-market instrument")
        state = json.loads(raw_state)
        if not isinstance(state, dict):
            raise OperatorSnapshotError("invalid multi-market execution state")
        stage = state.get("stage")
        if stage not in _MM_STAGES:
            raise OperatorSnapshotError("unknown multi-market execution stage")
        provider_status = state.get("provider_status")
        if provider_status is None:
            safe_status = "NOT_REPORTED"
        elif isinstance(provider_status, str):
            safe_status = _event_name(provider_status.upper())
        else:
            raise OperatorSnapshotError("invalid multi-market provider status")
        filled_qty = _number(state.get("cumulative_filled_qty"))
        is_unresolved = stage != "reconciled"
        by_lane[lane]["count"] += 1
        if is_unresolved:
            by_lane[lane]["unresolved"] += 1
            unresolved += 1
        if index < max_items:
            recent.append({
                "market_lane": lane,
                "instrument": instrument,
                "stage": stage,
                "provider_status": safe_status,
                "filled_qty": filled_qty,
                "updated_utc": _timestamp(updated),
            })
    return {
        "available": True,
        "count": len(joined),
        "unresolved": unresolved,
        "by_lane": by_lane,
        "recent": recent,
    }


def read_local_paper_snapshot(db_path: str | Path, *, max_items: int = 12) -> dict[str, object]:
    """Return a single consistent, sanitized snapshot via SQLite query-only mode.

    Does not invent account equity: no up-to-date mark is available to this view,
    so BTC inventory is shown in units, never mislabelled as live market value.
    """
    if not 1 <= max_items <= 50:
        raise ValueError("max_items outside allowed range")
    source = Path(db_path).expanduser().resolve(strict=False)
    if Path(db_path).expanduser().is_symlink():
        raise OperatorSnapshotError("symbolic-link database path is not allowed")
    if not source.exists() or not stat.S_ISREG(source.stat().st_mode):
        raise OperatorSnapshotError("paper ledger is missing or not a regular file")
    try:
        con = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=2.0,
                              isolation_level=None)
    except sqlite3.Error as exc:
        raise OperatorSnapshotError("cannot open read-only paper ledger") from exc
    try:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA query_only=ON")
        con.execute("PRAGMA busy_timeout=2000")
        con.execute("BEGIN")
        account = con.execute("""SELECT cash_usd, btc_qty, btc_cost_basis_usd,
                 realized_pnl_usd, fees_usd_equiv, peak_equity_usd,
                 session_start_equity_usd, updated_utc
                 FROM logical_portfolio WHERE singleton=1""").fetchone()
        control = con.execute("""SELECT operator_halted, halt_reason, updated_utc
                  FROM runtime_controls WHERE singleton=1""").fetchone()
        session = con.execute("""SELECT session_date_utc FROM risk_session_meta
                  WHERE singleton=1""").fetchone()
        if account is None or control is None or session is None:
            raise OperatorSnapshotError("required singleton ledger records missing")
        if control["operator_halted"] not in (0, 1):
            raise OperatorSnapshotError("invalid operator halt state")
        halt_reason = control["halt_reason"]
        if (not isinstance(halt_reason, str) or len(halt_reason) > 500
                or any(ch in halt_reason for ch in "\r\n\x00")):
            raise OperatorSnapshotError("invalid operator halt reason")
        amount_keys = ("cash_usd", "btc_qty", "btc_cost_basis_usd", "realized_pnl_usd",
                       "fees_usd_equiv", "peak_equity_usd", "session_start_equity_usd")
        amounts = {name: _number(account[name], nonnegative=name != "realized_pnl_usd")
                   for name in amount_keys}
        reservations = con.execute("""SELECT reserved_usd FROM drafts
                            WHERE status='DRAFT_APPROVED'""").fetchall()
        reserved_total = sum((Decimal(_number(row["reserved_usd"])) for row in reservations), Decimal(0))
        if reserved_total > Decimal(amounts["cash_usd"]):
            # Potentially an accounting issue; do not quietly present available cash as negative.
            raise OperatorSnapshotError("outstanding reservations exceed local cash")
        raw_states = con.execute("""SELECT state_json FROM paper_order_states
                            ORDER BY updated_utc DESC LIMIT ?""", (max_items,)).fetchall()
        order_count = con.execute("SELECT count(*) FROM paper_order_states").fetchone()[0]
        unresolved = 0
        order_rows = []
        allowed_stages = {"draft_approved", "submission_pending", "unknown_result",
                          "broker_accepted", "partially_filled", "broker_terminal_unreconciled",
                          "reconciled"}
        for row in con.execute("SELECT state_json FROM paper_order_states"):
            state = json.loads(row[0])
            stage = state.get("stage")
            if stage not in allowed_stages:
                raise OperatorSnapshotError("unknown paper order stage")
            if stage != "reconciled":
                unresolved += 1
        for row in raw_states:
            state = json.loads(row[0])
            stage = state.get("stage")
            if stage not in allowed_stages:
                raise OperatorSnapshotError("unknown paper order stage")
            order_rows.append({"stage": stage, "provider_status": _event_name(
                state.get("provider_status", "").upper()) if isinstance(state.get("provider_status"), str)
                else "NOT_REPORTED", "filled_qty": _number(state["cumulative_filled_qty"])})
        events = con.execute("""SELECT event_type, created_utc FROM events
                         ORDER BY seq DESC LIMIT ?""", (max_items,)).fetchall()
        applied_count = con.execute("SELECT count(*) FROM applied_provider_orders").fetchone()[0]
        pending_fees = con.execute("SELECT count(*) FROM pending_fee_audits").fetchone()[0]
        # Optional on older Phase 2G journals. Never CREATE/migrate on read.
        has_marks = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='logical_marks'").fetchone()
        mark = con.execute("SELECT mark_price,equity_usd,marked_utc FROM logical_marks WHERE singleton=1").fetchone() if has_marks else None
        last_mark = None
        if mark is not None:
            mark_price = _number(mark["mark_price"])
            if Decimal(mark_price) <= 0:
                raise OperatorSnapshotError("invalid recorded quote mark")
            last_mark = {"btc_usd": mark_price, "equity_usd": _number(mark["equity_usd"]),
                         "marked_utc": _timestamp(mark["marked_utc"]),
                         "source": "LAST_PERSISTED_PAPER_MARK_NOT_LIVE"}
        multimarket_execution = _multimarket_execution_snapshot(
            con, max_items=max_items
        )
        con.execute("COMMIT")
        return {
            "schema_version": 1,
            "source": "LOCAL_SQLITE_LEDGER_NOT_LIVE_MARKET_DATA",
            "mode": "ALPACA_PAPER_ONLY",
            "ledger_updated_utc": _timestamp(account["updated_utc"]),
            "operator_halted": bool(control["operator_halted"]),
            "halt_reason": halt_reason,
            "operator_control_updated_utc": _timestamp(control["updated_utc"]),
            "last_mark": last_mark,
            "session_date_utc": session["session_date_utc"],
            "logical": {**amounts, "reserved_usd": str(reserved_total),
                        "unreserved_cash_usd": str(Decimal(amounts["cash_usd"]) - reserved_total)},
            "paper_orders": {"count": order_count, "unresolved": unresolved,
                             "accounted_provider_orders": applied_count,
                             "pending_fee_audits": pending_fees, "recent": order_rows},
            "multimarket_execution": multimarket_execution,
            "recent_events": [{"type": _event_name(row["event_type"]),
                               "at_utc": _timestamp(row["created_utc"])} for row in events],
            "disclosure": "LOCAL PAPER JOURNAL ONLY. No verified live equity or strategy returns.",
        }
    except (sqlite3.Error, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        if isinstance(exc, OperatorSnapshotError):
            raise
        raise OperatorSnapshotError("paper ledger unreadable or inconsistent") from exc
    finally:
        con.close()

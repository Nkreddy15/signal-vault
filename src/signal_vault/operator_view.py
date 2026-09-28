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
        control = con.execute("""SELECT operator_halted, updated_utc
                  FROM runtime_controls WHERE singleton=1""").fetchone()
        session = con.execute("""SELECT session_date_utc FROM risk_session_meta
                  WHERE singleton=1""").fetchone()
        if account is None or control is None or session is None:
            raise OperatorSnapshotError("required singleton ledger records missing")
        if control["operator_halted"] not in (0, 1):
            raise OperatorSnapshotError("invalid operator halt state")
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
        con.execute("COMMIT")
        return {
            "schema_version": 1,
            "source": "LOCAL_SQLITE_LEDGER_NOT_LIVE_MARKET_DATA",
            "mode": "ALPACA_PAPER_ONLY",
            "ledger_updated_utc": _timestamp(account["updated_utc"]),
            "operator_halted": bool(control["operator_halted"]),
            "operator_control_updated_utc": _timestamp(control["updated_utc"]),
            "session_date_utc": session["session_date_utc"],
            "logical": {**amounts, "reserved_usd": str(reserved_total),
                        "unreserved_cash_usd": str(Decimal(amounts["cash_usd"]) - reserved_total)},
            "paper_orders": {"count": order_count, "unresolved": unresolved,
                             "accounted_provider_orders": applied_count,
                             "pending_fee_audits": pending_fees, "recent": order_rows},
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

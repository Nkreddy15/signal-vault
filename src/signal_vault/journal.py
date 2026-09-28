"""Durable, offline, SQLite order-DRAFT and event journal.

This file has deliberately NO broker submit method. It protects local proposal
idempotency/reservations across restarts, and is NOT a substitute for provider
balance reconciliation, PostgreSQL or an actual filled-order journal.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Mapping

from .alpaca_paper import PaperOrderDraft, build_non_executable_draft
from .domain import PortfolioSnapshot, TradeIntent, Side
from .risk import RiskEngine, RiskLimits

_SQL = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS drafts (
  client_order_id TEXT PRIMARY KEY,
  intent_hash TEXT NOT NULL,
  signal_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('DRAFT_APPROVED', 'VOID')),
  side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
  reserved_usd TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_utc TEXT NOT NULL,
  reference_price_usd TEXT
);
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  client_order_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  event_json TEXT NOT NULL,
  created_utc TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS events_immutable_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'audit events are immutable'); END;
CREATE TRIGGER IF NOT EXISTS events_immutable_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'audit events are immutable'); END;
"""


def _fingerprint(intent: TradeIntent) -> str:
    canonical = {"market": intent.market, "venue": intent.venue, "symbol": intent.symbol,
                 "side": intent.side.value if isinstance(intent.side, Side) else str(intent.side),
                 "notional": str(intent.notional_usd), "order_id": intent.client_order_id,
                 "signal": intent.signal_id, "quote_utc": intent.quote_timestamp.isoformat()}
    return sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()


class OfflineDraftJournal:
    def __init__(self, filename: str | Path) -> None:
        # :memory: is useful for tests only; no production persistence claim.
        self.connection = sqlite3.connect(str(filename), isolation_level=None, timeout=10)
        self.connection.executescript(_SQL)
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(drafts)")}
        if "reference_price_usd" not in columns:
            self.connection.execute("ALTER TABLE drafts ADD COLUMN reference_price_usd TEXT")
        self.risk = RiskEngine(RiskLimits(max_single_buy_usd=Decimal("15"),
                                          max_total_long_exposure_usd=Decimal("30")))

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "OfflineDraftJournal":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _reservations(self) -> Decimal:
        return sum((Decimal(v[0]) for v in self.connection.execute(
            "SELECT reserved_usd FROM drafts WHERE status='DRAFT_APPROVED'")), Decimal("0"))

    def total_reserved_usd(self) -> Decimal:
        return self._reservations()

    def record(self, intent: TradeIntent, portfolio: PortfolioSnapshot, *,
               checked_at: datetime, reference_price: Decimal,
               full_sell_quantity: Decimal | None = None) -> PaperOrderDraft:
        """Atomic local draft decision including all previous unvoided buy reserves.

        Must only be fed a current reconciled external snapshot that excludes
        this journal's *own* provisional reservations (to prevent double count).
        """
        if checked_at.tzinfo is None or checked_at.utcoffset() is None:
            raise ValueError("evaluation time must have timezone")
        if not portfolio.cash_usd.is_finite() or not portfolio.equity_usd.is_finite():
            raise ValueError("invalid proposed virtual snapshot")
        # The account begins with exactly $100; a legitimate audited profit
        # can make virtual equity exceed $100. Never accept a caller's *claim*
        # that it has grown: only a perfect match to our independently marked,
        # durably reconciled virtual ledger lifts the initial cap.
        if portfolio.cash_usd > Decimal("100") or portfolio.equity_usd > Decimal("100"):
            try:
                row = self.connection.execute("""SELECT virtual_cash,virtual_btc
                    FROM paper_virtual_budget WHERE singleton=1""").fetchone()
                mark = self.connection.execute("""SELECT current_equity,peak_equity,
                    session_start_equity,last_mark_price FROM paper_risk_marks
                    WHERE singleton=1""").fetchone()
            except sqlite3.OperationalError as exc:
                raise ValueError("offline paper snapshot exceeds logical $100 cap") from exc
            if not row or not mark:
                raise ValueError("offline paper snapshot exceeds logical $100 cap")
            btc_exposure = Decimal(row[1]) * reference_price
            if (Decimal(row[0]) != portfolio.cash_usd or
                Decimal(mark[0]) != portfolio.equity_usd or
                Decimal(mark[1]) != portfolio.peak_equity_usd or
                Decimal(mark[2]) != portfolio.session_start_equity_usd or
                Decimal(mark[3]) != reference_price or
                portfolio.long_positions_usd.get("BTC/USD",Decimal("0")) != btc_exposure):
                raise ValueError("paper gains require a matching independently audited virtual snapshot")
        key_hash = _fingerprint(intent)
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            existing = self.connection.execute(
                "SELECT intent_hash, status, payload_json, reference_price_usd FROM drafts WHERE client_order_id=?",
                (intent.client_order_id,)).fetchone()
            if existing:
                if existing[0] != key_hash:
                    raise ValueError("client order ID collision across different intents")
                if existing[1] == "VOID":
                    raise ValueError("void draft cannot be resubmitted with an old client ID")
                result = PaperOrderDraft(intent.client_order_id, json.loads(existing[2]),
                                         reference_price_usd=Decimal(existing[3]) if existing[3] is not None else None)
                self.connection.execute("COMMIT")
                return result
            reserved = self._reservations()
            adjusted = replace(portfolio,
                               open_buy_notional_usd=portfolio.open_buy_notional_usd + reserved)
            draft = build_non_executable_draft(intent, adjusted, checked_at=checked_at,
                                               reference_price=reference_price,
                                               full_sell_quantity=full_sell_quantity,
                                               risk_engine=self.risk)
            reserve = intent.notional_usd if intent.side is Side.BUY else Decimal("0")
            at = checked_at.astimezone(timezone.utc).isoformat()
            self.connection.execute(
                """INSERT INTO drafts
                    (client_order_id,intent_hash,signal_id,status,side,reserved_usd,
                     payload_json,created_utc,reference_price_usd)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                (intent.client_order_id, key_hash, intent.signal_id, "DRAFT_APPROVED",
                 intent.side.value, str(reserve), json.dumps(draft.payload, sort_keys=True), at,
                 str(reference_price)))
            self.connection.execute("INSERT INTO events (client_order_id,event_type,event_json,created_utc) VALUES (?,?,?,?)",
                                    (intent.client_order_id, "DRAFT_APPROVED",
                                     json.dumps({"signal": intent.signal_id, "reserved_usd": str(reserve)}), at))
            self.connection.execute("COMMIT")
            return draft
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def void(self, client_order_id: str, *, reason: str, at: datetime) -> None:
        if not reason.strip() or at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("reason and timezone-aware event time are required")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            old = self.connection.execute("SELECT status FROM drafts WHERE client_order_id=?",
                                          (client_order_id,)).fetchone()
            if old is None:
                raise KeyError("unknown draft")
            if old[0] != "DRAFT_APPROVED":
                raise ValueError("draft already void")
            # A durable paper submission makes the draft non-voidable forever.
            # Otherwise a caller could release RESERVED capital while an order
            # is pending or after an ambiguous transport timeout. Fail closed
            # even if the paper order was already reconciled: its audit history
            # must remain distinguishable from an intentionally unused draft.
            has_paper_table = self.connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='paper_order_states'"
            ).fetchone()
            if has_paper_table and self.connection.execute(
                "SELECT 1 FROM paper_order_states WHERE client_order_id=?",
                (client_order_id,),
            ).fetchone():
                raise PermissionError("submitted paper draft cannot be voided; reconcile provider order")
            self.connection.execute("UPDATE drafts SET status='VOID', reserved_usd='0' WHERE client_order_id=?",
                                    (client_order_id,))
            self.connection.execute("INSERT INTO events (client_order_id,event_type,event_json,created_utc) VALUES (?,?,?,?)",
                                    (client_order_id, "DRAFT_VOIDED", json.dumps({"reason": reason}),
                                     at.astimezone(timezone.utc).isoformat()))
            self.connection.execute("COMMIT")
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def expire_unsent_drafts(self, *, at: datetime, ttl_seconds: int = 120) -> tuple[str, ...]:
        """Release only strictly UNSUBMITTED expired proposals, never real orders.

        A process crash after recording a proposal but before the research-cycle
        checkpoint must not hold the virtual capital forever. Any draft with a
        matching paper_order_states row is permanently excluded, even if it is
        UNKNOWN or terminal-but-unreconciled.
        """
        if at.tzinfo is None or at.utcoffset() is None or not 90 <= ttl_seconds <= 86400:
            raise ValueError("aware cleanup time and sane TTL required")
        cutoff = at.astimezone(timezone.utc) - timedelta(seconds=ttl_seconds)
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            paper_table = bool(self.connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='paper_order_states'"
            ).fetchone())
            expired = []
            for client_id, created in self.connection.execute(
                "SELECT client_order_id,created_utc FROM drafts WHERE status='DRAFT_APPROVED'"):
                stamp = datetime.fromisoformat(created)
                if stamp.tzinfo is None or stamp.astimezone(timezone.utc) >= cutoff:
                    continue
                if paper_table and self.connection.execute(
                    "SELECT 1 FROM paper_order_states WHERE client_order_id=?",
                    (client_id,),
                ).fetchone():
                    continue
                self.connection.execute("UPDATE drafts SET status='VOID',reserved_usd='0' WHERE client_order_id=?",
                                        (client_id,))
                self.connection.execute("""INSERT INTO events
                    (client_order_id,event_type,event_json,created_utc) VALUES (?,?,?,?)""",
                    (client_id,"UNSENT_DRAFT_EXPIRED",
                     json.dumps({"ttl_seconds":ttl_seconds},sort_keys=True),
                     at.astimezone(timezone.utc).isoformat()))
                expired.append(client_id)
            self.connection.execute("COMMIT")
            return tuple(expired)
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def recent_events(self) -> list[Mapping[str, object]]:
        return [{"seq": seq, "client_order_id": key, "type": typ,
                 "details": json.loads(data), "created_utc": at}
                for seq, key, typ, data, at in self.connection.execute(
                    "SELECT seq,client_order_id,event_type,event_json,created_utc FROM events ORDER BY seq")]

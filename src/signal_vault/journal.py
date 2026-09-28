"""Durable, offline, SQLite order-DRAFT and event journal.

This file has deliberately NO broker submit method. It protects local proposal
idempotency/reservations across restarts, and is NOT a substitute for provider
balance reconciliation, PostgreSQL or an actual filled-order journal.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
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
  created_utc TEXT NOT NULL
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
               full_sell_quantity: Decimal | None = None,
               logical_ledger_verified: bool = False) -> PaperOrderDraft:
        """Atomic local draft decision including all previous unvoided buy reserves.

        Must only be fed a current reconciled external snapshot that excludes
        this journal's *own* provisional reservations (to prevent double count).
        """
        if checked_at.tzinfo is None or checked_at.utcoffset() is None:
            raise ValueError("evaluation time must have timezone")
        # Untrusted offline callers cannot accidentally feed Alpaca's large default
        # paper balance into the logical $100 experiment. The persistent runtime
        # may pass a separately verified Signal Vault ledger snapshot whose equity
        # can legitimately rise above $100 through trading gains.
        if not portfolio.cash_usd.is_finite() or not portfolio.equity_usd.is_finite():
            raise ValueError("invalid offline paper snapshot")
        if (not logical_ledger_verified and
                (portfolio.cash_usd > Decimal("100") or portfolio.equity_usd > Decimal("100"))):
            raise ValueError("unverified offline paper snapshot exceeds logical $100 initial capital")
        key_hash = _fingerprint(intent)
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            existing = self.connection.execute(
                "SELECT intent_hash, status, payload_json FROM drafts WHERE client_order_id=?",
                (intent.client_order_id,)).fetchone()
            if existing:
                if existing[0] != key_hash:
                    raise ValueError("client order ID collision across different intents")
                if existing[1] == "VOID":
                    raise ValueError("void draft cannot be resubmitted with an old client ID")
                result = PaperOrderDraft(intent.client_order_id, json.loads(existing[2]))
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
                "INSERT INTO drafts VALUES (?,?,?,?,?,?,?,?)",
                (intent.client_order_id, key_hash, intent.signal_id, "DRAFT_APPROVED",
                 intent.side.value, str(reserve), json.dumps(draft.payload, sort_keys=True), at))
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
            self.connection.execute("UPDATE drafts SET status='VOID', reserved_usd='0' WHERE client_order_id=?",
                                    (client_order_id,))
            self.connection.execute("INSERT INTO events (client_order_id,event_type,event_json,created_utc) VALUES (?,?,?,?)",
                                    (client_order_id, "DRAFT_VOIDED", json.dumps({"reason": reason}),
                                     at.astimezone(timezone.utc).isoformat()))
            self.connection.execute("COMMIT")
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def recent_events(self) -> list[Mapping[str, object]]:
        return [{"seq": seq, "client_order_id": key, "type": typ,
                 "details": json.loads(data), "created_utc": at}
                for seq, key, typ, data, at in self.connection.execute(
                    "SELECT seq,client_order_id,event_type,event_json,created_utc FROM events ORDER BY seq")]

"""Persisted paper-order state transitions and draft linkage; still NO network POST.

The future provider adapter must begin a submission in this database BEFORE it
sends an order, and after any timeout must perform a provider lookup by the
EXACT client_order_id. Blind retry is intentionally unsupported. The caller
may only confirm reconciliation after separately verifying provider order,
position and cash records. A passing fake test is not real provider evidence.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping

from .alpaca_paper import PaperOrderDraft
from .journal import OfflineDraftJournal
from .paper_order_state import PaperOrderState, BrokerObservation, Stage


def _state_json(value: PaperOrderState) -> str:
    return json.dumps({"client_order_id": value.client_order_id,
                       "stage": value.stage.value,
                       "broker_order_id": value.broker_order_id,
                       "provider_status": value.provider_status,
                       "cumulative_filled_qty": str(value.cumulative_filled_qty),
                       "filled_avg_price": str(value.filled_avg_price) if value.filled_avg_price is not None else None,
                       "reconciled": value.reconciled}, sort_keys=True)


def _parse_state(raw: str) -> PaperOrderState:
    data = json.loads(raw)
    return PaperOrderState(
        client_order_id=data["client_order_id"], stage=Stage(data["stage"]),
        broker_order_id=data["broker_order_id"], provider_status=data["provider_status"],
        cumulative_filled_qty=Decimal(data["cumulative_filled_qty"]),
        filled_avg_price=Decimal(data["filled_avg_price"]) if data["filled_avg_price"] is not None else None,
        reconciled=data["reconciled"],
    )


class PersistentPaperOrderStore:
    """Single-SQLite-file conservative local prototype. Never a provider client."""

    def __init__(self, filename: str | Path) -> None:
        self.journal = OfflineDraftJournal(filename)
        self.connection = self.journal.connection
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS paper_order_states (
                client_order_id TEXT PRIMARY KEY,
                state_json TEXT NOT NULL,
                updated_utc TEXT NOT NULL,
                FOREIGN KEY(client_order_id) REFERENCES drafts(client_order_id)
            )
        """)

    def close(self) -> None:
        self.journal.close()

    def __enter__(self) -> "PersistentPaperOrderStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _state_in_transaction(self, client_order_id: str) -> PaperOrderState:
        row = self.connection.execute("SELECT state_json FROM paper_order_states WHERE client_order_id=?",
                                      (client_order_id,)).fetchone()
        if row is None:
            raise KeyError("paper order not registered")
        result = _parse_state(row[0])
        if result.client_order_id != client_order_id:
            raise ValueError("persistent order identity mismatch; halt")
        return result

    def get(self, client_order_id: str) -> PaperOrderState:
        return self._state_in_transaction(client_order_id)

    def has_unresolved_provider_order(self) -> bool:
        return any(_parse_state(x[0]).blocks_new_execution for x in self.connection.execute(
            "SELECT state_json FROM paper_order_states"))

    def _save(self, state: PaperOrderState, event: str, details: Mapping[str, object], at: datetime) -> None:
        stamp = at.astimezone(timezone.utc).isoformat()
        self.connection.execute("UPDATE paper_order_states SET state_json=?, updated_utc=? WHERE client_order_id=?",
                                (_state_json(state), stamp, state.client_order_id))
        self.connection.execute("""INSERT INTO events (client_order_id,event_type,event_json,created_utc)
                                   VALUES (?,?,?,?)""",
                                (state.client_order_id, event, json.dumps(details, sort_keys=True), stamp))

    def begin_submission(self, draft: PaperOrderDraft, *, at: datetime) -> PaperOrderState:
        """Atomically reserve the right to TRY ONE external paper POST later.

        No POST is implemented here. If a crash follows this commit, the next
        worker must perform provider lookup before making any other attempt.
        """
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("timezone required")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            row = self.connection.execute("SELECT status,payload_json FROM drafts WHERE client_order_id=?",
                                          (draft.client_order_id,)).fetchone()
            if not row or row[0] != "DRAFT_APPROVED" or json.loads(row[1]) != dict(draft.payload):
                raise PermissionError("only a matching, durable, Guardian-approved draft may proceed")
            if self.connection.execute("SELECT 1 FROM paper_order_states WHERE client_order_id=?",
                                       (draft.client_order_id,)).fetchone():
                raise ValueError("order ID already entered submission; NEVER post again")
            if self.has_unresolved_provider_order():
                raise PermissionError("an order is unresolved; reconcile before any other order")
            new = PaperOrderState(draft.client_order_id).start_submission()
            self.connection.execute("INSERT INTO paper_order_states VALUES (?,?,?)",
                                    (draft.client_order_id, _state_json(new), at.astimezone(timezone.utc).isoformat()))
            self.connection.execute("""INSERT INTO events (client_order_id,event_type,event_json,created_utc)
                                       VALUES (?,?,?,?)""",
                                    (draft.client_order_id, "SUBMISSION_PENDING",
                                     json.dumps({"payload_recorded": True}), at.astimezone(timezone.utc).isoformat()))
            self.connection.execute("COMMIT")
            return new
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def mark_unknown(self, client_order_id: str, *, at: datetime) -> PaperOrderState:
        """A timeout is ambiguous. Keep reserved funds; never infer no fill."""
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("timezone required")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            new = self._state_in_transaction(client_order_id).mark_transport_uncertain()
            self._save(new, "UNKNOWN_RESULT", {"requires_provider_lookup": True}, at)
            self.connection.execute("COMMIT")
            return new
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def recover_inflight_pending_after_restart(self, *, at: datetime) -> tuple[str, ...]:
        """Treat pre-crash SUBMISSION_PENDING as UNKNOWN, not safe-to-resubmit.

        Startup must run this step before scanning/any new order. A network
        request may have reached the broker before process termination.
        """
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("timezone required")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            uncertain: list[str] = []
            for (raw,) in self.connection.execute("SELECT state_json FROM paper_order_states"):
                old = _parse_state(raw)
                if old.stage is Stage.SUBMISSION_PENDING:
                    new = old.mark_transport_uncertain()
                    self._save(new, "RESTART_RECOVERY_UNKNOWN",
                               {"requires_provider_lookup": True}, at)
                    uncertain.append(old.client_order_id)
            self.connection.execute("COMMIT")
            return tuple(uncertain)
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def observe_provider(self, observation: BrokerObservation, *, at: datetime) -> PaperOrderState:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("timezone required")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            old = self._state_in_transaction(observation.client_order_id)
            new = old.observe(observation)
            if new != old:
                self._save(new, "PROVIDER_OBSERVATION",
                           {"broker_order_id": new.broker_order_id, "status": new.provider_status,
                            "cumulative_filled_qty": str(new.cumulative_filled_qty)}, at)
            self.connection.execute("COMMIT")
            return new
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def finish_reconciliation(self, client_order_id: str, *, at: datetime,
                              provider_cash_verified: bool, provider_position_verified: bool,
                              provider_order_verified: bool) -> PaperOrderState:
        """Release local reservation only AFTER independent provider checks.

        Provider-verification booleans must come from a separate authenticated
        auditor; this prototype deliberately doesn't pretend it performed one.
        """
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("timezone required")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            new = self._state_in_transaction(client_order_id).confirm_reconciled(
                provider_cash_verified=provider_cash_verified,
                provider_position_verified=provider_position_verified,
                provider_order_verified=provider_order_verified)
            self._save(new, "PROVIDER_RECONCILED",
                       {"provider_cash": True, "provider_position": True, "provider_order": True}, at)
            self.connection.execute("UPDATE drafts SET reserved_usd='0' WHERE client_order_id=?",
                                    (client_order_id,))
            self.connection.execute("COMMIT")
            return new
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

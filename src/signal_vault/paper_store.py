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
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Mapping

from .alpaca_paper import PaperOrderDraft
from .journal import OfflineDraftJournal
from .paper_order_state import PaperOrderState, BrokerObservation, Stage
from .paper_audit import PaperHoldings, validate_terminal_evidence, EPS_BTC, EPS_USD


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
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS paper_account_baselines (
                client_order_id TEXT PRIMARY KEY,
                baseline_json TEXT NOT NULL,
                FOREIGN KEY(client_order_id) REFERENCES drafts(client_order_id)
            )
        """)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS paper_virtual_budget (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                account_id TEXT NOT NULL,
                last_provider_cash TEXT NOT NULL,
                last_provider_btc TEXT NOT NULL,
                virtual_cash TEXT NOT NULL,
                virtual_btc TEXT NOT NULL,
                updated_utc TEXT NOT NULL
            )
        """)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS operator_controls (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                halted INTEGER NOT NULL CHECK (halted IN (0,1)),
                reason TEXT NOT NULL,
                updated_utc TEXT NOT NULL
            )
        """)
        self.connection.execute("""INSERT OR IGNORE INTO operator_controls
            VALUES(1,0,'initial paper-only operating state','1970-01-01T00:00:00+00:00')""")

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

    def budget_snapshot(self) -> Mapping[str, str] | None:
        """Isolated virtual $100 paper subledger, NOT the broker default balance."""
        row = self.connection.execute("""
            SELECT account_id,last_provider_cash,last_provider_btc,
                   virtual_cash,virtual_btc,updated_utc
              FROM paper_virtual_budget WHERE singleton=1
        """).fetchone()
        if row is None:
            return None
        return dict(zip(("account_id","last_provider_cash","last_provider_btc",
                         "virtual_cash","virtual_btc","updated_utc"), row))

    def is_operator_halted(self) -> bool:
        row = self.connection.execute("SELECT halted FROM operator_controls WHERE singleton=1").fetchone()
        # Missing or corrupt safety controls must STOP, never silently resume.
        return row is None or row[0] != 0

    def set_operator_halt(self, halted: bool, *, reason: str, at: datetime) -> None:
        """Durably block new broker submissions, including across restarts.

        Halt does not pretend to cancel existing external orders: the auditor
        must still poll/resolve a provider order and notify the operator.
        """
        if not isinstance(halted, bool) or not isinstance(reason, str) or not reason.strip():
            raise ValueError("an explicit operator action and reason are required")
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("aware audit event time required")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            if not halted and self.has_unresolved_provider_order():
                raise PermissionError("cannot resume while a provider paper order is unresolved")
            self.connection.execute("""UPDATE operator_controls SET halted=?,reason=?,updated_utc=?
                                       WHERE singleton=1""",
                                    (int(halted), reason, at.astimezone(timezone.utc).isoformat()))
            self.connection.execute("""INSERT INTO events (client_order_id,event_type,event_json,created_utc)
                                       VALUES (?,?,?,?)""",
                                    ("_operator_", "HALT_ENABLED" if halted else "HALT_CLEARED",
                                     json.dumps({"reason":reason}, sort_keys=True),
                                     at.astimezone(timezone.utc).isoformat()))
            self.connection.execute("COMMIT")
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

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

    def begin_submission(self, draft: PaperOrderDraft, *, at: datetime,
                         baseline: PaperHoldings) -> PaperOrderState:
        """Persist verified before-order cash/BTC baseline BEFORE the one POST.

        No POST is implemented here. If a crash follows this commit, the next
        worker must perform provider lookup before making any other attempt.
        """
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("timezone required")
        if not isinstance(baseline, PaperHoldings):
            raise ValueError("paper provider baseline required before submission")
        if baseline.observed_at > at or at - baseline.observed_at > timedelta(seconds=90):
            raise ValueError("stale/future provider baseline: no submission")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            row = self.connection.execute("SELECT status,payload_json,reference_price_usd,created_utc FROM drafts WHERE client_order_id=?",
                                          (draft.client_order_id,)).fetchone()
            if (not row or row[0] != "DRAFT_APPROVED" or
                json.loads(row[1]) != dict(draft.payload) or
                row[2] is None or draft.reference_price_usd is None or
                Decimal(row[2]) != draft.reference_price_usd):
                raise PermissionError("only a matching, durable, Guardian-approved draft may proceed")
            created_at = datetime.fromisoformat(row[3])
            if created_at > at or at - created_at > timedelta(seconds=90):
                raise PermissionError("durable paper proposal is stale; do not submit")
            if self.connection.execute("SELECT 1 FROM paper_order_states WHERE client_order_id=?",
                                       (draft.client_order_id,)).fetchone():
                raise ValueError("order ID already entered submission; NEVER post again")
            if self.is_operator_halted():
                raise PermissionError("persistent operator emergency HALT is engaged")
            if self.has_unresolved_provider_order():
                raise PermissionError("an order is unresolved; reconcile before any other order")
            # The provider's paper balance may default to $100,000. Anchor a
            # separate immutable $100 test budget and track only OUR independently
            # reconciled order deltas. Deposits/manual orders that change the
            # actual provider cash/BTC between our trades block further POSTs.
            budget = self.budget_snapshot()
            if budget is None:
                if baseline.btc_qty != 0 or baseline.cash_usd < Decimal("100"):
                    raise PermissionError("initial isolated paper account needs zero BTC and >= $100 cash")
                virtual_cash, virtual_btc = Decimal("100"), Decimal("0")
                self.connection.execute("""INSERT INTO paper_virtual_budget VALUES(1,?,?,?,?,?,?)""",
                    (baseline.account_id, str(baseline.cash_usd), str(baseline.btc_qty),
                     str(virtual_cash), str(virtual_btc), at.astimezone(timezone.utc).isoformat()))
            else:
                if (budget["account_id"] != baseline.account_id or
                    abs(Decimal(budget["last_provider_cash"]) - baseline.cash_usd) > EPS_USD or
                    abs(Decimal(budget["last_provider_btc"]) - baseline.btc_qty) > EPS_BTC):
                    raise PermissionError("external paper holdings changed without our reconciliation")
                virtual_cash, virtual_btc = (Decimal(budget["virtual_cash"]),
                                             Decimal(budget["virtual_btc"]))
            if draft.payload["side"] == "buy":
                # Independently mark *our* virtual $100 subaccount at the
                # originally risk-checked quote; ignore default paper buying
                # power. A stale/fabricated external PortfolioSnapshot cannot
                # trick the executor into bypassing the base loss pause.
                marked_equity = virtual_cash + virtual_btc * draft.reference_price_usd
                if marked_equity <= Decimal("97"):
                    raise PermissionError("isolated virtual account lost >= $3 from initial $100; halt new buys")
                amount = Decimal(draft.payload["notional"])
                if amount > virtual_cash:
                    raise PermissionError("virtual $100 paper cash balance exhausted")
                if (virtual_btc * draft.reference_price_usd + amount > Decimal("30")):
                    raise PermissionError("independently tracked BTC exposure exceeds fixed $30 cap")
            elif Decimal(draft.payload["qty"]) > virtual_btc + EPS_BTC:
                raise PermissionError("sell quantity exceeds reconciled virtual BTC holdings")
            new = PaperOrderState(draft.client_order_id).start_submission()
            self.connection.execute("INSERT INTO paper_order_states VALUES (?,?,?)",
                                    (draft.client_order_id, _state_json(new), at.astimezone(timezone.utc).isoformat()))
            self.connection.execute("INSERT INTO paper_account_baselines VALUES (?,?)",
                                    (draft.client_order_id, json.dumps(baseline.canonical(), sort_keys=True)))
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
                              post: PaperHoldings,
                              provider_order: Mapping[str, object]) -> PaperOrderState:
        """Release reservation ONLY after independent source evidence reconciles.

        Caller-supplied success booleans are expressly NOT accepted. The before
        snapshot is captured durably before POST. This check must be run using
        fresh paper account, position and exact order GETs; inconsistent evidence
        leaves the order UNRECONCILED, retaining the capital reservation.
        """
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("timezone required")
        if not isinstance(post, PaperHoldings):
            raise ValueError("source-derived post-trade holdings required")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            state = self._state_in_transaction(client_order_id)
            baseline_row = self.connection.execute(
                "SELECT baseline_json FROM paper_account_baselines WHERE client_order_id=?",
                (client_order_id,)).fetchone()
            draft_row = self.connection.execute(
                "SELECT payload_json FROM drafts WHERE client_order_id=?",
                (client_order_id,)).fetchone()
            if baseline_row is None or draft_row is None:
                raise ValueError("missing durable baseline or original approved order")
            baseline = PaperHoldings.from_canonical(json.loads(baseline_row[0]))
            digest = validate_terminal_evidence(state, json.loads(draft_row[0]), baseline,
                                                post, provider_order, at=at)
            budget = self.budget_snapshot()
            if (budget is None or budget["account_id"] != baseline.account_id or
                abs(Decimal(budget["last_provider_cash"]) - baseline.cash_usd) > EPS_USD or
                abs(Decimal(budget["last_provider_btc"]) - baseline.btc_qty) > EPS_BTC):
                raise ValueError("paper virtual ledger not anchored to this provider baseline")
            next_cash = Decimal(budget["virtual_cash"]) + post.cash_usd - baseline.cash_usd
            next_btc = Decimal(budget["virtual_btc"]) + post.btc_qty - baseline.btc_qty
            if next_cash < -EPS_USD or next_btc < -EPS_BTC:
                raise ValueError("reconciled broker order exceeded isolated virtual capital")
            if next_cash < 0: next_cash = Decimal("0")  # provider rounding only
            if next_btc < 0: next_btc = Decimal("0")
            new = state.confirm_reconciled(provider_cash_verified=True,
                                           provider_position_verified=True,
                                           provider_order_verified=True)
            self._save(new, "PROVIDER_EVIDENCE_RECONCILED",
                       {"evidence_sha256": digest, "source": "alpaca-paper"}, at)
            self.connection.execute("UPDATE drafts SET reserved_usd='0' WHERE client_order_id=?",
                                    (client_order_id,))
            self.connection.execute("""UPDATE paper_virtual_budget
                 SET last_provider_cash=?,last_provider_btc=?,virtual_cash=?,virtual_btc=?,updated_utc=?
                 WHERE singleton=1""",
                (str(post.cash_usd),str(post.btc_qty),str(next_cash),str(next_btc),
                 at.astimezone(timezone.utc).isoformat()))
            self.connection.execute("COMMIT")
            return new
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

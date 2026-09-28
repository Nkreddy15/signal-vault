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
from .domain import PortfolioSnapshot
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
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS logical_portfolio (
                singleton INTEGER PRIMARY KEY CHECK (singleton=1),
                cash_usd TEXT NOT NULL,
                btc_qty TEXT NOT NULL,
                btc_cost_basis_usd TEXT NOT NULL,
                realized_pnl_usd TEXT NOT NULL,
                fees_usd_equiv TEXT NOT NULL,
                peak_equity_usd TEXT NOT NULL,
                session_start_equity_usd TEXT NOT NULL,
                updated_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS applied_provider_orders (
                client_order_id TEXT PRIMARY KEY,
                broker_order_id TEXT NOT NULL UNIQUE,
                side TEXT NOT NULL CHECK(side IN ('buy','sell')),
                filled_qty TEXT NOT NULL,
                avg_price TEXT,
                fee_usd_equiv TEXT NOT NULL,
                provider_btc_qty TEXT NOT NULL,
                applied_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pending_fee_audits (
                client_order_id TEXT PRIMARY KEY,
                broker_order_id TEXT NOT NULL UNIQUE,
                provisional_fee_usd_equiv TEXT NOT NULL,
                inferred_btc_fee_qty TEXT NOT NULL,
                created_utc TEXT NOT NULL,
                FOREIGN KEY(client_order_id) REFERENCES applied_provider_orders(client_order_id)
            );
            CREATE TABLE IF NOT EXISTS risk_session_meta (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                session_date_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runtime_controls (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                operator_halted INTEGER NOT NULL CHECK(operator_halted IN (0,1)),
                halt_reason TEXT NOT NULL,
                updated_utc TEXT NOT NULL
            );
        """)
        self.connection.execute(
            """INSERT OR IGNORE INTO logical_portfolio VALUES
               (1,'100','0','0','0','0','100','100',?)""",
            (datetime.now(timezone.utc).isoformat(),))
        now = datetime.now(timezone.utc)
        self.connection.execute("INSERT OR IGNORE INTO risk_session_meta VALUES (1,?)",
                                (now.date().isoformat(),))
        self.connection.execute(
            "INSERT OR IGNORE INTO runtime_controls VALUES (1,0,'',?)",
            (now.isoformat(),))

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

    def list_states(self) -> tuple[PaperOrderState, ...]:
        """Stable snapshot for recovery/audit orchestration; never mutates state."""
        return tuple(_parse_state(row[0]) for row in self.connection.execute(
            "SELECT state_json FROM paper_order_states ORDER BY client_order_id"))


    def record_logical_draft(self, intent, portfolio: PortfolioSnapshot, *,
                             checked_at: datetime, reference_price: Decimal,
                             full_sell_quantity: Decimal | None = None):
        """Record a draft only from this store's internally verified logical ledger.

        This is the bridge that permits genuine trading gains to lift logical
        equity above the initial $100 without ever treating Alpaca's default
        simulated account balance as Signal Vault capital.
        """
        if checked_at.tzinfo is None or checked_at.utcoffset() is None:
            raise ValueError("timezone required")
        if not isinstance(reference_price, Decimal) or not reference_price.is_finite() or reference_price <= 0:
            raise ValueError("valid reference price required")
        account = self.logical_account()
        expected_position = account["btc_qty"] * reference_price
        reported_position = portfolio.long_positions_usd.get("BTC/USD", Decimal("0"))
        if portfolio.cash_usd != account["cash_usd"] or reported_position != expected_position:
            raise ValueError("portfolio snapshot is not derived from the logical ledger")
        if portfolio.equity_usd != account["cash_usd"] + expected_position:
            raise ValueError("logical ledger equity mismatch")
        return self.journal.record(
            intent, portfolio, checked_at=checked_at, reference_price=reference_price,
            full_sell_quantity=full_sell_quantity, logical_ledger_verified=True)

    def get_draft_payload(self, client_order_id: str) -> Mapping[str, str]:
        row = self.connection.execute(
            "SELECT payload_json FROM drafts WHERE client_order_id=?", (client_order_id,)
        ).fetchone()
        if row is None:
            raise KeyError("paper draft not found")
        value = json.loads(row[0])
        if not isinstance(value, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                                              for k, v in value.items()):
            raise ValueError("persistent paper draft payload is malformed")
        return value


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

    def operator_halt(self) -> tuple[bool, str]:
        row = self.connection.execute(
            "SELECT operator_halted,halt_reason FROM runtime_controls WHERE singleton=1").fetchone()
        if row is None:
            raise ValueError("runtime controls missing")
        return bool(row[0]), str(row[1])

    def set_operator_halt(self, halted: bool, *, reason: str, at: datetime) -> None:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("timezone required")
        if not isinstance(halted, bool):
            raise ValueError("halted must be boolean")
        clean_reason = reason.strip()
        if halted and not clean_reason:
            raise ValueError("halt reason required")
        if len(clean_reason) > 500 or any(ch in clean_reason for ch in "\r\n\x00"):
            raise ValueError("invalid halt reason")
        stamp = at.astimezone(timezone.utc).isoformat()
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.connection.execute(
                "UPDATE runtime_controls SET operator_halted=?,halt_reason=?,updated_utc=? WHERE singleton=1",
                (1 if halted else 0, clean_reason if halted else "", stamp))
            self.connection.execute(
                "INSERT INTO events (client_order_id,event_type,event_json,created_utc) VALUES (?,?,?,?)",
                ("SYSTEM", "OPERATOR_HALT" if halted else "OPERATOR_RESUME",
                 json.dumps({"reason": clean_reason if halted else ""}, sort_keys=True), stamp))
            self.connection.execute("COMMIT")
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def logical_account(self) -> Mapping[str, Decimal]:
        row = self.connection.execute(
            "SELECT cash_usd,btc_qty,btc_cost_basis_usd,realized_pnl_usd,fees_usd_equiv,peak_equity_usd,session_start_equity_usd FROM logical_portfolio WHERE singleton=1"
        ).fetchone()
        if row is None:
            raise ValueError("logical portfolio missing")
        values = tuple(Decimal(x) for x in row)
        if any(not x.is_finite() or x < 0 for x in (values[0], values[1], values[2], values[4], values[5], values[6])):
            raise ValueError("logical portfolio corrupt")
        return {"cash_usd": values[0], "btc_qty": values[1],
                "btc_cost_basis_usd": values[2], "realized_pnl_usd": values[3],
                "fees_usd_equiv": values[4], "peak_equity_usd": values[5],
                "session_start_equity_usd": values[6]}

    def mark_portfolio(self, *, mark_price: Decimal, at: datetime,
                       reset_session: bool = False, halted: bool = False) -> PortfolioSnapshot:
        """Build the Guardian snapshot from Signal Vault's own logical $100 ledger.

        The provider paper account's large default balance is deliberately ignored.
        Peak equity is persisted; session start changes only when the scheduler
        explicitly starts a new UTC risk session.
        """
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("timezone required")
        if not isinstance(mark_price, Decimal) or not mark_price.is_finite() or mark_price <= 0:
            raise ValueError("valid BTC/USD mark price required")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            account = self.logical_account()
            cash = account["cash_usd"]; qty = account["btc_qty"]
            position_value = qty * mark_price
            equity = cash + position_value
            peak = max(account["peak_equity_usd"], equity)
            utc_at = at.astimezone(timezone.utc)
            session_row = self.connection.execute(
                "SELECT session_date_utc FROM risk_session_meta WHERE singleton=1").fetchone()
            if session_row is None:
                raise ValueError("risk session metadata missing")
            today = utc_at.date().isoformat()
            new_day = session_row[0] != today
            session = equity if (reset_session or new_day) else account["session_start_equity_usd"]
            if reset_session or new_day:
                self.connection.execute(
                    "UPDATE risk_session_meta SET session_date_utc=? WHERE singleton=1", (today,))
            self.connection.execute(
                "UPDATE logical_portfolio SET peak_equity_usd=?,session_start_equity_usd=?,updated_utc=? WHERE singleton=1",
                (str(peak), str(session), utc_at.isoformat()))
            pending = self.journal.total_reserved_usd()
            self.connection.execute("COMMIT")
            positions = {"BTC/USD": position_value} if qty > 0 else {}
            return PortfolioSnapshot(equity_usd=equity, cash_usd=cash, peak_equity_usd=peak,
                                     session_start_equity_usd=session,
                                     open_buy_notional_usd=pending,
                                     long_positions_usd=positions, halted=halted)
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def finish_reconciliation_with_accounting(
        self, client_order_id: str, *, at: datetime, provider_btc_qty: Decimal,
        fee_usd_equiv: Decimal, usd_fee_amount: Decimal,
        provider_cash_verified: bool, provider_position_verified: bool,
        provider_order_verified: bool, fee_pending: bool = False,
        inferred_btc_fee_qty: Decimal = Decimal("0"),
    ) -> PaperOrderState:
        """Atomically apply a verified terminal fill to the logical $100 ledger.

        The Alpaca paper account may contain a much larger simulated balance.
        Signal Vault therefore tracks only its own initial $100 plus realized
        results. Provider position quantity is authoritative for BTC inventory.
        """
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("timezone required")
        for value, name in ((provider_btc_qty, "provider BTC quantity"),
                            (fee_usd_equiv, "fee USD equivalent"),
                            (usd_fee_amount, "USD fee"),
                            (inferred_btc_fee_qty, "inferred BTC fee")):
            if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
                raise ValueError(f"invalid {name}")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            old = self._state_in_transaction(client_order_id)
            new = old.confirm_reconciled(
                provider_cash_verified=provider_cash_verified,
                provider_position_verified=provider_position_verified,
                provider_order_verified=provider_order_verified)
            payload = self.get_draft_payload(client_order_id)
            side = payload.get("side")
            if side not in ("buy", "sell") or old.broker_order_id is None:
                raise ValueError("invalid persistent order identity")
            prior = self.connection.execute(
                "SELECT broker_order_id,side,filled_qty,avg_price,fee_usd_equiv,provider_btc_qty FROM applied_provider_orders WHERE client_order_id=?",
                (client_order_id,)).fetchone()
            if prior is not None:
                raise ValueError("provider order accounting already applied")
            account = self.logical_account()
            cash = account["cash_usd"]; btc = account["btc_qty"]; cost = account["btc_cost_basis_usd"]
            realized = account["realized_pnl_usd"]; fees = account["fees_usd_equiv"]
            qty = old.cumulative_filled_qty
            avg = old.filled_avg_price
            if qty > 0 and (avg is None or not avg.is_finite() or avg <= 0):
                raise ValueError("filled order requires valid provider average price")
            gross = qty * avg if qty else Decimal("0")
            if side == "buy":
                if provider_btc_qty < btc or provider_btc_qty > btc + qty:
                    raise ValueError("provider BTC inventory is inconsistent with buy fill")
                cash_new = cash - gross
                if cash_new < 0:
                    raise ValueError("logical $100 ledger would overspend cash")
                btc_new = provider_btc_qty
                cost_new = cost + gross
                realized_new = realized
            else:
                if qty > btc or provider_btc_qty > btc:
                    raise ValueError("provider BTC inventory is inconsistent with sell fill")
                if qty and btc <= 0:
                    raise ValueError("cannot account sell without logical BTC inventory")
                allocated_cost = (cost * qty / btc) if qty else Decimal("0")
                proceeds = gross - usd_fee_amount
                if proceeds < 0:
                    raise ValueError("USD fee exceeds sell proceeds")
                cash_new = cash + proceeds
                btc_new = provider_btc_qty
                cost_new = cost - allocated_cost
                realized_new = realized + proceeds - allocated_cost
                if btc_new == 0 and abs(cost_new) < Decimal("0.00000001"):
                    cost_new = Decimal("0")
            fees_new = fees + fee_usd_equiv
            stamp = at.astimezone(timezone.utc).isoformat()
            self.connection.execute(
                """UPDATE logical_portfolio SET cash_usd=?,btc_qty=?,btc_cost_basis_usd=?,
                   realized_pnl_usd=?,fees_usd_equiv=?,updated_utc=? WHERE singleton=1""",
                tuple(map(str, (cash_new, btc_new, cost_new, realized_new, fees_new))) + (stamp,))
            self.connection.execute(
                "INSERT INTO applied_provider_orders VALUES (?,?,?,?,?,?,?,?)",
                (client_order_id, old.broker_order_id, side, str(qty),
                 str(avg) if avg is not None else None, str(fee_usd_equiv),
                 str(provider_btc_qty), stamp))
            if fee_pending:
                if side != "buy" or usd_fee_amount != 0 or inferred_btc_fee_qty < 0:
                    raise ValueError("only BTC/USD buy crypto-fee audit may remain pending")
                self.connection.execute(
                    "INSERT INTO pending_fee_audits VALUES (?,?,?,?,?)",
                    (client_order_id, old.broker_order_id, str(fee_usd_equiv),
                     str(inferred_btc_fee_qty), stamp))
            self._save(new, "PROVIDER_RECONCILED_ACCOUNTED",
                       {"provider_cash": True, "provider_position": True,
                        "provider_order": True, "logical_cash_usd": str(cash_new),
                        "logical_btc_qty": str(btc_new), "fee_usd_equiv": str(fee_usd_equiv)}, at)
            self.connection.execute("UPDATE drafts SET reserved_usd='0' WHERE client_order_id=?",
                                    (client_order_id,))
            self.connection.execute("COMMIT")
            return new
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def pending_fee_order_ids(self) -> tuple[str, ...]:
        return tuple(row[0] for row in self.connection.execute(
            "SELECT client_order_id FROM pending_fee_audits ORDER BY created_utc,client_order_id"))

    def settle_pending_buy_fee(self, client_order_id: str, *, at: datetime,
                               final_fee_usd_equiv: Decimal,
                               final_btc_fee_qty: Decimal,
                               final_usd_fee_amount: Decimal) -> None:
        """Replace a provisional inferred BUY fee with provider fee activity.

        The net BTC inventory already proved the BTC fee quantity. If the later
        provider CFEE reports a different base quantity, halt rather than rewrite
        history. Only the USD-equivalent valuation may be adjusted.
        """
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("timezone required")
        for value in (final_fee_usd_equiv, final_btc_fee_qty, final_usd_fee_amount):
            if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
                raise ValueError("invalid final fee")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            row = self.connection.execute(
                "SELECT broker_order_id,provisional_fee_usd_equiv,inferred_btc_fee_qty FROM pending_fee_audits WHERE client_order_id=?",
                (client_order_id,)).fetchone()
            if row is None:
                raise KeyError("no pending fee audit for order")
            broker_id, provisional, inferred = row
            provisional = Decimal(provisional); inferred = Decimal(inferred)
            applied = self.connection.execute(
                "SELECT side FROM applied_provider_orders WHERE client_order_id=? AND broker_order_id=?",
                (client_order_id, broker_id)).fetchone()
            if applied is None or applied[0] != "buy":
                raise ValueError("pending fee identity mismatch")
            if final_usd_fee_amount != 0:
                raise ValueError("BTC/USD buy fee unexpectedly posted in USD")
            if final_btc_fee_qty != inferred:
                raise ValueError("posted BTC fee quantity differs from position-inferred fee; halt")
            delta = final_fee_usd_equiv - provisional
            account = self.logical_account()
            new_total = account["fees_usd_equiv"] + delta
            if new_total < 0:
                raise ValueError("fee settlement would make total fees negative")
            stamp = at.astimezone(timezone.utc).isoformat()
            self.connection.execute(
                "UPDATE logical_portfolio SET fees_usd_equiv=?,updated_utc=? WHERE singleton=1",
                (str(new_total), stamp))
            self.connection.execute(
                "UPDATE applied_provider_orders SET fee_usd_equiv=? WHERE client_order_id=?",
                (str(final_fee_usd_equiv), client_order_id))
            self.connection.execute("DELETE FROM pending_fee_audits WHERE client_order_id=?",
                                    (client_order_id,))
            self.connection.execute(
                "INSERT INTO events (client_order_id,event_type,event_json,created_utc) VALUES (?,?,?,?)",
                (client_order_id, "PROVIDER_FEE_FINALIZED",
                 json.dumps({"broker_order_id": broker_id,
                             "final_fee_usd_equiv": str(final_fee_usd_equiv),
                             "fee_adjustment_usd": str(delta)}, sort_keys=True), stamp))
            self.connection.execute("COMMIT")
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

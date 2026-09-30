"""Pure, fail-closed order receipt state machine for PAPER-mode broker integration.

There are no HTTP/network calls here. The future executor must persist transitions
atomically and verify provider observations. UNKNOWN_RESULT never permits a blind
retry. A broker `filled` notification is NOT portfolio reconciliation.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum


class Stage(str, Enum):
    DRAFT_APPROVED = "draft_approved"
    SUBMISSION_PENDING = "submission_pending"
    UNKNOWN_RESULT = "unknown_result"
    BROKER_ACCEPTED = "broker_accepted"
    PARTIALLY_FILLED = "partially_filled"
    BROKER_TERMINAL_UNRECONCILED = "broker_terminal_unreconciled"
    RECONCILED = "reconciled"


TERMINAL_PROVIDER_STATES = frozenset({"filled", "canceled", "expired", "rejected"})
ACTIVE_PROVIDER_STATES = frozenset({"new", "accepted", "pending_new", "partially_filled"})


@dataclass(frozen=True)
class BrokerObservation:
    """A parsed authoritative lookup/stream record, never a generated AI claim."""
    client_order_id: str
    broker_order_id: str
    provider_status: str
    cumulative_filled_qty: Decimal = Decimal("0")
    filled_avg_price: Decimal | None = None


@dataclass(frozen=True)
class PaperOrderState:
    client_order_id: str
    stage: Stage = Stage.DRAFT_APPROVED
    broker_order_id: str | None = None
    provider_status: str | None = None
    cumulative_filled_qty: Decimal = Decimal("0")
    filled_avg_price: Decimal | None = None
    reconciled: bool = False

    def start_submission(self) -> "PaperOrderState":
        if self.stage is not Stage.DRAFT_APPROVED:
            raise ValueError("submission already started; do not submit twice")
        return replace(self, stage=Stage.SUBMISSION_PENDING)

    def mark_transport_uncertain(self) -> "PaperOrderState":
        if self.stage is not Stage.SUBMISSION_PENDING:
            raise ValueError("only uncertain submissions may become UNKNOWN_RESULT")
        return replace(self, stage=Stage.UNKNOWN_RESULT)

    def attach_uncertain_broker_identity(self, broker_order_id: str) -> "PaperOrderState":
        """Retain a provider order ID while status/fills remain unresolved.

        This does NOT convert UNKNOWN_RESULT into accepted/filled and cannot
        introduce provider status or fill economics. It exists only so an
        authenticated lookup can recover the exact provider order later.
        """
        if self.stage is not Stage.UNKNOWN_RESULT:
            raise ValueError("provider identity attachment requires UNKNOWN_RESULT")
        if not isinstance(broker_order_id, str) or not broker_order_id.strip():
            raise ValueError("nonempty provider order id required")
        if self.broker_order_id is not None and self.broker_order_id != broker_order_id:
            raise ValueError("provider order id already bound to another value")
        if (self.provider_status is not None or self.cumulative_filled_qty != 0
                or self.filled_avg_price is not None):
            raise ValueError("uncertain identity cannot fabricate provider economics")
        return replace(self, broker_order_id=broker_order_id)

    def observe(self, receipt: BrokerObservation) -> "PaperOrderState":
        """Mismatched and regressing provider records cause hard errors.

        A paper `filled` status does not clear portfolio reservations until a
        separate account/order/position reconciliation is completed.
        """
        if self.stage not in (Stage.SUBMISSION_PENDING, Stage.UNKNOWN_RESULT,
                              Stage.BROKER_ACCEPTED, Stage.PARTIALLY_FILLED,
                              Stage.BROKER_TERMINAL_UNRECONCILED):
            raise ValueError("provider observation not permitted in this stage")
        if receipt.client_order_id != self.client_order_id or not receipt.broker_order_id:
            raise ValueError("provider order ID mismatch / missing broker ID")
        if self.broker_order_id is not None and self.broker_order_id != receipt.broker_order_id:
            raise ValueError("broker order ID changed for same client ID")
        if receipt.provider_status not in ACTIVE_PROVIDER_STATES | TERMINAL_PROVIDER_STATES:
            raise ValueError("unsupported provider state: fail closed")
        qty = receipt.cumulative_filled_qty
        if not isinstance(qty, Decimal) or not qty.is_finite() or qty < 0:
            raise ValueError("invalid cumulative provider quantity")
        if qty < self.cumulative_filled_qty:
            raise ValueError("provider cumulative filled quantity regressed")
        px = receipt.filled_avg_price
        if qty > 0 and (not isinstance(px, Decimal) or not px.is_finite() or px <= 0):
            raise ValueError("nonzero provider fill requires a valid average price")
        if qty == 0 and px is not None:
            raise ValueError("unexpected average price with zero fill")
        if self.stage is Stage.BROKER_TERMINAL_UNRECONCILED:
            if (receipt.provider_status != self.provider_status or
                qty != self.cumulative_filled_qty or px != self.filled_avg_price):
                raise ValueError("terminal provider observation changed; halt and investigate")
            return self
        if receipt.provider_status == "partially_filled":
            if qty <= 0:
                raise ValueError("partial fill requires nonzero provider quantity")
            new_stage = Stage.PARTIALLY_FILLED
        elif receipt.provider_status in TERMINAL_PROVIDER_STATES:
            if receipt.provider_status == "filled" and qty <= 0:
                raise ValueError("filled status without verified cumulative quantity")
            new_stage = Stage.BROKER_TERMINAL_UNRECONCILED
        else:
            if self.stage is Stage.PARTIALLY_FILLED:
                raise ValueError("provider status regressed from partial fill")
            if qty != 0:
                raise ValueError("accepted state unexpectedly contains fill")
            new_stage = Stage.BROKER_ACCEPTED
        return replace(self, stage=new_stage, broker_order_id=receipt.broker_order_id,
                       provider_status=receipt.provider_status, cumulative_filled_qty=qty,
                       filled_avg_price=px)

    def confirm_reconciled(self, *, provider_cash_verified: bool,
                           provider_position_verified: bool,
                           provider_order_verified: bool) -> "PaperOrderState":
        if self.stage is not Stage.BROKER_TERMINAL_UNRECONCILED:
            raise ValueError("terminal broker state required before reconciliation")
        if not (provider_cash_verified and provider_position_verified and provider_order_verified):
            raise ValueError("cash, position and order must ALL reconcile")
        return replace(self, stage=Stage.RECONCILED, reconciled=True)

    @property
    def blocks_new_execution(self) -> bool:
        """Only fully reconciled provider-terminal states unblock the next order."""
        return self.stage not in (Stage.RECONCILED,)

"""Read-only Alpaca PAPER reconciliation for crypto and US-equity orders.

This module never submits, cancels, replaces, or retries an order. It resolves
the durable shared execution journal only from an authoritative PAPER order
lookup by client_order_id. A missing lookup remains blocking; terminal broker
state remains unreconciled until account/cash/position surfaces are separately
verified.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Mapping, Protocol

from .multimarket_execution_journal import MultiMarketExecutionJournal
from .paper_order_state import (
    ACTIVE_PROVIDER_STATES,
    TERMINAL_PROVIDER_STATES,
    BrokerObservation,
    PaperOrderState,
    Stage,
)


class AlpacaPaperOrderReader(Protocol):
    def lookup_order(self, client_order_id: str) -> Mapping[str, object] | None: ...


def _decimal(raw: object, *, name: str) -> Decimal:
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid Alpaca {name}") from exc
    if not value.is_finite() or value < 0:
        raise ValueError(f"invalid Alpaca {name}")
    return value


def alpaca_paper_lookup_observation(
    payload: Mapping[str, object],
    *,
    expected_client_order_id: str,
    expected_instrument: str,
) -> BrokerObservation:
    if not isinstance(payload, Mapping):
        raise ValueError("Alpaca paper order lookup must be an object")
    if payload.get("client_order_id") != expected_client_order_id:
        raise ValueError("Alpaca paper client order id mismatch")
    if payload.get("symbol") != expected_instrument:
        raise ValueError("Alpaca paper instrument mismatch")

    broker_order_id = payload.get("id")
    status = payload.get("status")
    if not isinstance(broker_order_id, str) or not broker_order_id:
        raise ValueError("Alpaca paper broker order id missing")
    if not isinstance(status, str):
        raise ValueError("Alpaca paper order status missing")
    status = status.lower()
    if status not in ACTIVE_PROVIDER_STATES | TERMINAL_PROVIDER_STATES:
        raise ValueError("unsupported Alpaca paper order status")

    qty = _decimal(payload.get("filled_qty", "0"), name="filled_qty")
    raw_avg = payload.get("filled_avg_price")
    if qty == 0:
        if raw_avg not in (None, ""):
            raise ValueError("zero-fill Alpaca order unexpectedly has average fill price")
        avg = None
    else:
        avg = _decimal(raw_avg, name="filled_avg_price")
        if avg <= 0:
            raise ValueError("nonzero Alpaca fill requires positive average price")

    return BrokerObservation(
        client_order_id=expected_client_order_id,
        broker_order_id=broker_order_id,
        provider_status=status,
        cumulative_filled_qty=qty,
        filled_avg_price=avg,
    )


@dataclass(frozen=True)
class AlpacaPaperReconciliationOutcome:
    state: PaperOrderState
    lookup_found: bool
    lookup_performed: bool
    provider_terminal: bool
    full_account_reconciliation_still_required: bool
    new_execution_blocked: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "stage": self.state.stage.value,
            "provider_status": self.state.provider_status,
            "lookup_found": self.lookup_found,
            "lookup_performed": self.lookup_performed,
            "provider_terminal": self.provider_terminal,
            "full_account_reconciliation_still_required":
                self.full_account_reconciliation_still_required,
            "new_execution_blocked": self.new_execution_blocked,
            "network_action": "READ_ONLY_ORDER_LOOKUP",
            "order_submission": "DISABLED",
            "live_trading": "UNAVAILABLE",
        }


def reconcile_alpaca_paper_order_lookup(
    *,
    journal: MultiMarketExecutionJournal,
    reader: AlpacaPaperOrderReader,
    client_order_id: str,
    expected_instrument: str,
    at: datetime,
) -> AlpacaPaperReconciliationOutcome:
    state = journal.get_state(client_order_id)
    if state.stage is Stage.RECONCILED:
        raise ValueError("reconciled execution does not require provider recovery lookup")

    provider_order = reader.lookup_order(client_order_id)
    if provider_order is None:
        if state.stage is Stage.SUBMISSION_PENDING:
            state = journal.mark_unknown(client_order_id, at=at)
        return AlpacaPaperReconciliationOutcome(
            state=state,
            lookup_found=False,
            lookup_performed=True,
            provider_terminal=False,
            full_account_reconciliation_still_required=False,
            new_execution_blocked=state.blocks_new_execution,
        )

    observation = alpaca_paper_lookup_observation(
        provider_order,
        expected_client_order_id=client_order_id,
        expected_instrument=expected_instrument,
    )
    state = journal.observe_provider(observation, at=at)
    terminal = state.stage is Stage.BROKER_TERMINAL_UNRECONCILED
    return AlpacaPaperReconciliationOutcome(
        state=state,
        lookup_found=True,
        lookup_performed=True,
        provider_terminal=terminal,
        full_account_reconciliation_still_required=terminal,
        new_execution_blocked=state.blocks_new_execution,
    )

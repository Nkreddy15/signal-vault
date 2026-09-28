"""Offline dry-run broker; no HTTP, keys, or real/paper provider order submission."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .domain import TradeIntent
from .risk import RiskDecision


@dataclass(frozen=True)
class OrderReceipt:
    client_order_id: str
    status: str
    broker_order_id: str | None
    note: str


class BrokerAdapter(Protocol):
    def submit(self, intent: TradeIntent, decision: RiskDecision) -> OrderReceipt: ...


class LocalDryRunBroker:
    """Records approved intents only. No fills, cash changes, or external effects.

    Retries with the same idempotency key return the same receipt. Reusing a key
    for a different order is always an error, not an opportunity to re-submit.
    """

    def __init__(self) -> None:
        self._intents: dict[str, TradeIntent] = {}
        self._receipts: dict[str, OrderReceipt] = {}

    def submit(self, intent: TradeIntent, decision: RiskDecision) -> OrderReceipt:
        if not decision.approved:
            raise PermissionError(f"Risk engine rejected proposal: {decision.reasons}")
        prior = self._intents.get(intent.client_order_id)
        if prior is not None:
            if prior != intent:
                raise ValueError("idempotency key collision with conflicting proposal")
            return self._receipts[intent.client_order_id]
        receipt = OrderReceipt(
            client_order_id=intent.client_order_id,
            status="DRY_RUN_RECORDED_NOT_FILLED",
            broker_order_id=None,
            note="Offline record only. No broker network connection or trading occurred.",
        )
        self._intents[intent.client_order_id] = intent
        self._receipts[intent.client_order_id] = receipt
        return receipt

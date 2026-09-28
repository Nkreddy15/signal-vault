"""Independent provider fill audit for paper orders.

This module validates immutable Alpaca FILL activities against the terminal
order state. It does not submit, cancel, transfer, or automatically mark an
order reconciled. Cash/position/fee reconciliation remains a separate gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence

from .paper_order_state import PaperOrderState, Stage


def _decimal(value: object, field: str, *, allow_zero: bool = False) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"invalid fill {field}") from exc
    if not result.is_finite() or (result < 0 if allow_zero else result <= 0):
        raise ValueError(f"invalid fill {field}")
    return result


@dataclass(frozen=True)
class FillAudit:
    order_id: str
    symbol: str
    side: str
    cumulative_qty: Decimal
    weighted_avg_price: Decimal | None
    activity_ids: tuple[str, ...]
    verified: bool


def audit_fill_activities(state: PaperOrderState,
                          activities: Sequence[Mapping[str, object]]) -> FillAudit:
    if state.stage is not Stage.BROKER_TERMINAL_UNRECONCILED:
        raise ValueError("terminal unreconciled provider order required")
    if not state.broker_order_id:
        raise ValueError("terminal state missing provider order ID")

    expected_qty = state.cumulative_filled_qty
    if expected_qty == 0:
        if activities:
            raise ValueError("zero-fill terminal order unexpectedly has FILL activities")
        return FillAudit(state.broker_order_id, "BTC/USD", "unknown", Decimal("0"), None, (), True)
    if not activities:
        raise ValueError("filled/partially-filled terminal order lacks FILL activities")

    qty_total = Decimal("0")
    notional_total = Decimal("0")
    side: str | None = None
    seen: set[str] = set()
    ids: list[str] = []
    for activity in activities:
        if activity.get("activity_type") != "FILL" or activity.get("type") not in ("fill", "partial_fill"):
            raise ValueError("unexpected paper activity type")
        if activity.get("order_id") != state.broker_order_id:
            raise ValueError("fill activity belongs to a different order")
        symbol = str(activity.get("symbol", "")).replace("/", "")
        if symbol != "BTCUSD":
            raise ValueError("fill activity is not BTC/USD")
        activity_id = activity.get("id")
        if not isinstance(activity_id, str) or not activity_id or activity_id in seen:
            raise ValueError("missing or duplicate fill activity ID")
        seen.add(activity_id); ids.append(activity_id)
        current_side = activity.get("side")
        if current_side not in ("buy", "sell") or (side is not None and current_side != side):
            raise ValueError("inconsistent fill side")
        side = current_side
        qty = _decimal(activity.get("qty"), "quantity")
        price = _decimal(activity.get("price"), "price")
        qty_total += qty
        notional_total += qty * price

    if qty_total != expected_qty:
        raise ValueError("FILL activity quantity does not equal terminal cumulative fill")
    average = notional_total / qty_total
    if state.filled_avg_price is None:
        raise ValueError("terminal state lacks average fill price")
    # Provider order average can differ by sub-cent precision/rounding. Keep a
    # tight absolute tolerance rather than rewriting either provider fact.
    if abs(average - state.filled_avg_price) > Decimal("0.01"):
        raise ValueError("FILL activity weighted price does not match terminal order")
    return FillAudit(state.broker_order_id, "BTC/USD", side or "unknown", qty_total,
                     average, tuple(ids), True)

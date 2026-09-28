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


@dataclass(frozen=True)
class CryptoFeeAudit:
    order_id: str
    fee_usd_equivalent: Decimal
    btc_fee_qty: Decimal
    usd_fee_amount: Decimal
    activity_ids: tuple[str, ...]
    final: bool


def audit_crypto_fee_activities(order_id: str, activities: Sequence[Mapping[str, object]]) -> CryptoFeeAudit:
    """Validate provider fee activities and preserve fee currency semantics.

    CFEE is recorded as negative crypto quantity and converted to USD-equivalent
    with provider price. FEE is negative USD net_amount. Empty results are not
    final because Alpaca documents crypto fees as potentially posted end-of-day.
    """
    if not order_id:
        raise ValueError("provider order ID required")
    if not activities:
        return CryptoFeeAudit(order_id, Decimal("0"), Decimal("0"), Decimal("0"), (), False)
    equivalent = Decimal("0")
    btc_fee = Decimal("0")
    usd_fee = Decimal("0")
    ids: list[str] = []
    seen: set[str] = set()
    for activity in activities:
        activity_id = activity.get("id")
        if not isinstance(activity_id, str) or not activity_id or activity_id in seen:
            raise ValueError("missing or duplicate fee activity ID")
        seen.add(activity_id); ids.append(activity_id)
        if activity.get("order_id") not in (None, order_id):
            raise ValueError("fee activity belongs to a different order")
        typ = activity.get("activity_type")
        symbol = str(activity.get("symbol", "")).replace("/", "")
        if symbol and symbol != "BTCUSD":
            raise ValueError("fee activity is not BTC/USD")
        try:
            if typ == "CFEE":
                qty = Decimal(str(activity.get("qty")))
                price = Decimal(str(activity.get("price")))
                if not qty.is_finite() or qty >= 0 or not price.is_finite() or price <= 0:
                    raise ValueError
                btc_fee += -qty
                equivalent += (-qty) * price
            elif typ == "FEE":
                amount = Decimal(str(activity.get("net_amount")))
                if not amount.is_finite() or amount >= 0:
                    raise ValueError
                usd_fee += -amount
                equivalent += -amount
            else:
                raise ValueError("unexpected fee activity type")
        except (InvalidOperation, ValueError, TypeError) as exc:
            if isinstance(exc, ValueError) and str(exc) == "unexpected fee activity type":
                raise
            raise ValueError("malformed crypto fee activity") from exc
    return CryptoFeeAudit(order_id, equivalent, btc_fee, usd_fee, tuple(ids), True)

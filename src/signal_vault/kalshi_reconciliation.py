"""Pure Kalshi order/fill reconciliation into the shared paper state machine.

Consumes authenticated provider payloads already fetched by a separate demo
transport. It performs no network access, signing, credential loading, or order
submission.

Kalshi V2 order status values are normalized conservatively:
- resting + zero fills -> accepted
- resting + some fills -> partially_filled
- executed -> filled (requires remaining_count_fp == 0 and nonzero fills)
- canceled -> canceled

Any nonzero cumulative fill requires exact matching fill rows and an
authoritative weighted YES-dollar execution price.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence

from .paper_order_state import BrokerObservation

_ALLOWED_STATUS={"resting","canceled","executed"}


def _decimal(value:object,*,name:str)->Decimal:
    try:
        number=Decimal(str(value))
    except (InvalidOperation,TypeError,ValueError) as exc:
        raise ValueError(f"invalid Kalshi {name}") from exc
    if not number.is_finite() or number<0:
        raise ValueError(f"invalid Kalshi {name}")
    return number


def kalshi_order_and_fills_observation(
    *,
    order_payload:Mapping[str,object],
    fills_payload:Mapping[str,object],
    expected_client_order_id:str,
) -> BrokerObservation:
    if not isinstance(order_payload,Mapping):
        raise ValueError("Kalshi order payload must be an object")
    order=order_payload.get("order")
    if not isinstance(order,Mapping):
        raise ValueError("Kalshi order response missing order object")

    order_id=order.get("order_id")
    client_id=order.get("client_order_id")
    status=order.get("status")
    if not isinstance(order_id,str) or not order_id:
        raise ValueError("Kalshi order id missing")
    if client_id!=expected_client_order_id:
        raise ValueError("Kalshi client order id mismatch")
    if status not in _ALLOWED_STATUS:
        raise ValueError("unsupported Kalshi order status")

    fill_count=_decimal(order.get("fill_count_fp"),name="fill_count_fp")
    remaining=_decimal(order.get("remaining_count_fp"),name="remaining_count_fp")
    initial=_decimal(order.get("initial_count_fp"),name="initial_count_fp")
    if initial<=0 or fill_count+remaining!=initial:
        raise ValueError("Kalshi order counts do not reconcile")

    fills=fills_payload.get("fills") if isinstance(fills_payload,Mapping) else None
    if not isinstance(fills,list):
        raise ValueError("Kalshi fills response missing fills array")

    total_qty=Decimal("0")
    total_value=Decimal("0")
    seen_ids=set()
    for item in fills:
        if not isinstance(item,Mapping):
            raise ValueError("malformed Kalshi fill")
        if item.get("order_id")!=order_id:
            raise ValueError("Kalshi fill belongs to another order")
        fill_id=item.get("fill_id")
        if not isinstance(fill_id,str) or not fill_id or fill_id in seen_ids:
            raise ValueError("missing or duplicate Kalshi fill id")
        seen_ids.add(fill_id)
        qty=_decimal(item.get("count_fp"),name="fill count")
        price=_decimal(item.get("yes_price_dollars"),name="YES fill price")
        if qty<=0 or price<=0 or price>=1:
            raise ValueError("invalid Kalshi fill quantity or price")
        total_qty+=qty
        total_value+=qty*price

    if total_qty!=fill_count:
        raise ValueError("Kalshi order fill count differs from fill records")

    avg_price=None
    if fill_count>0:
        if not fills:
            raise ValueError("nonzero Kalshi fill count requires fill records")
        avg_price=total_value/total_qty

    if status=="resting":
        provider_status="partially_filled" if fill_count>0 else "accepted"
        if remaining<=0:
            raise ValueError("resting Kalshi order must have remaining quantity")
    elif status=="executed":
        if fill_count<=0 or remaining!=0:
            raise ValueError("executed Kalshi order must be fully filled")
        provider_status="filled"
    else:
        provider_status="canceled"

    return BrokerObservation(
        client_order_id=expected_client_order_id,
        broker_order_id=order_id,
        provider_status=provider_status,
        cumulative_filled_qty=fill_count,
        filled_avg_price=avg_price,
    )

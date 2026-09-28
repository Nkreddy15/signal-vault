"""Strict provider-reported BTC/USD trading constraints.

Alpaca's asset response can expose dynamic `min_order_size`,
`min_trade_increment` and `price_increment`. We parse rather than guess these
values, and fail closed when the provider omits/mangles them before submission.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping


def _positive_decimal(value: object, name: str) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError(f"missing/invalid {name}")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"missing/invalid {name}") from exc
    if not result.is_finite() or result <= 0:
        raise ValueError(f"missing/invalid {name}")
    return result


@dataclass(frozen=True)
class CryptoVenueRules:
    symbol: str
    min_order_size: Decimal       # base BTC quantity, provider reported
    min_trade_increment: Decimal  # base BTC quantity increment
    price_increment: Decimal      # provider reported quote/notional increment

    @classmethod
    def from_asset(cls, asset: Mapping[str, object]) -> "CryptoVenueRules":
        if (asset.get("symbol") != "BTC/USD" or asset.get("class") != "crypto" or
                asset.get("status") != "active" or asset.get("tradable") is not True or
                asset.get("fractionable") is not True):
            raise ValueError("BTC/USD paper asset is not eligible")
        rules = cls(
            symbol="BTC/USD",
            min_order_size=_positive_decimal(asset.get("min_order_size"), "min_order_size"),
            min_trade_increment=_positive_decimal(asset.get("min_trade_increment"), "min_trade_increment"),
            price_increment=_positive_decimal(asset.get("price_increment"), "price_increment"),
        )
        if rules.min_order_size.as_tuple().exponent < -9 or rules.min_trade_increment.as_tuple().exponent < -9:
            raise ValueError("provider BTC quantity precision exceeds supported 9 decimals")
        return rules

    def minimum_notional_at(self, reference_price: Decimal) -> Decimal:
        if not isinstance(reference_price, Decimal) or not reference_price.is_finite() or reference_price <= 0:
            raise ValueError("invalid reference price")
        return self.min_order_size * reference_price

    def validate_buy_notional(self, notional: Decimal, reference_price: Decimal) -> None:
        if not isinstance(notional, Decimal) or not notional.is_finite() or notional <= 0:
            raise ValueError("invalid buy notional")
        minimum = self.minimum_notional_at(reference_price)
        # Alpaca documents the USD-pair minimum as dynamically corresponding to
        # about $10. Provider metadata wins; we never silently increase an order.
        if notional < minimum:
            raise ValueError("buy is below provider-reported dynamic minimum")
        if notional > Decimal("15"):
            raise ValueError("buy exceeds Signal Vault paper Guardian envelope")
        if notional != notional.quantize(Decimal("0.01")):
            raise ValueError("buy notional must use exact cent precision")

    def validate_sell_qty(self, qty: Decimal, reference_price: Decimal) -> None:
        if not isinstance(qty, Decimal) or not qty.is_finite() or qty <= 0:
            raise ValueError("invalid sell quantity")
        if qty < self.min_order_size:
            raise ValueError("sell quantity is below provider-reported minimum")
        # Quantity must lie on min_trade_increment grid. Decimal modulo is exact.
        if qty % self.min_trade_increment != 0:
            raise ValueError("sell quantity does not match provider trade increment")
        if qty * reference_price < self.minimum_notional_at(reference_price):
            raise ValueError("sell notional is below provider-reported minimum")

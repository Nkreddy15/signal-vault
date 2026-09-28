"""BTC/USD paper venue size checks and EXPLICIT dust-preserving exit previews.

Pure functions. No broker call, no silent order upsize, and no assumption that
selling rounded base quantity fully exits a fee-reduced crypto position.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Mapping


def _positive(source: object, label: str) -> Decimal:
    try:
        value=Decimal(str(source))
    except (TypeError,ValueError,ArithmeticError) as exc:
        raise ValueError(f"invalid paper venue {label}") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError(f"non-positive paper venue {label}")
    return value


@dataclass(frozen=True)
class BtcVenueRules:
    minimum_base_qty: Decimal
    base_trade_step: Decimal
    usd_price_step: Decimal

    @classmethod
    def from_asset(cls, asset: Mapping[str, object]) -> "BtcVenueRules":
        if (not isinstance(asset, Mapping) or asset.get("symbol") != "BTC/USD" or
            asset.get("class") != "crypto" or asset.get("status") != "active" or
            asset.get("tradable") is not True or asset.get("fractionable") is not True):
            raise ValueError("asset metadata is not current confirmed BTC/USD")
        return cls(_positive(asset.get("min_order_size"), "minimum base qty"),
                   _positive(asset.get("min_trade_increment"), "base step"),
                   _positive(asset.get("price_increment"), "USD price step"))

    def check_buy(self, *, notional_usd: Decimal, reference_price: Decimal) -> None:
        px=_positive(reference_price,"reference price")
        n=_positive(notional_usd,"buy notional")
        if n.as_tuple().exponent < -2:
            raise ValueError("USD buy must have max two decimal places")
        if n/px < self.minimum_base_qty:
            raise PermissionError("buy below current provider minimum; no automatic upsize")

    def preview_sell(self, *, held_base_qty: Decimal, reference_price: Decimal) -> "SellPreview":
        """Show feasible lower-multiple SELL and residual DUST; submit NOTHING.

        This is NOT approval to round an existing full-exit order down behind
        the owner's back. A future operating mandate must approve retain-and-
        notify behavior before using this preview to create a fresh quantity
        intent. Current writer still rejects mis-sized direct full-exit drafts.
        """
        available=_positive(held_base_qty,"held BTC")
        px=_positive(reference_price,"reference price")
        steps=(available/self.base_trade_step).to_integral_value(rounding=ROUND_DOWN)
        executable=steps*self.base_trade_step
        residual=available-executable
        if executable < self.minimum_base_qty:
            return SellPreview(available,Decimal('0'),available,Decimal('0'),False,
                               "DUST_ONLY: held quantity below permissible source venue step/minimum")
        estimated=executable*px
        # The current Alpaca planning baseline is at least $10 equivalent.
        if estimated < Decimal('10'):
            return SellPreview(available,Decimal('0'),available,Decimal('0'),False,
                               "DUST_ONLY: source-allowed stepped quantity below estimated USD venue minimum")
        return SellPreview(available,executable,residual,estimated,True,
                           "PREVIEW ONLY: any residual BTC remains held and must be monitored")


@dataclass(frozen=True)
class SellPreview:
    held_base_qty: Decimal
    executable_base_qty: Decimal
    residual_dust_qty: Decimal
    estimated_sell_usd: Decimal
    can_prepare_dust_aware_intent: bool
    note: str

"""Venue-neutral proposal and portfolio risk inputs; money uses Decimal throughout."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Mapping


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class TradeIntent:
    market: str                  # e.g. crypto; explicit before adding equity / events
    venue: str                   # e.g. alpaca; dry-run does not connect to this venue
    symbol: str                  # e.g. BTC/USD
    side: Side
    notional_usd: Decimal        # amount proposed, NOT assumed amount actually filled
    client_order_id: str         # idempotency key
    signal_id: str               # immutable strategy evidence reference
    quote_timestamp: datetime   # timezone-aware source timestamp


@dataclass(frozen=True)
class PortfolioSnapshot:
    equity_usd: Decimal
    cash_usd: Decimal
    peak_equity_usd: Decimal
    session_start_equity_usd: Decimal
    open_buy_notional_usd: Decimal = Decimal("0")
    long_positions_usd: Mapping[str, Decimal] = field(default_factory=dict)
    halted: bool = False

    @property
    def current_long_exposure_usd(self) -> Decimal:
        return sum(self.long_positions_usd.values(), Decimal("0"))

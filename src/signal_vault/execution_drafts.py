"""Compile selected Phase 162 PAPER intents into bounded provider drafts.

This is a deterministic translation layer only. It never performs network I/O,
never reads credentials, and never submits orders. Provider-specific executors
still require durable journaling, fresh provider preflight, shared risk receipt,
and explicit PAPER/DEMO acknowledgement before a POST.

Kalshi V2 uses one YES-side order book:
- bid = buy YES
- ask = sell YES, economically equivalent to buying NO at 1-price
The event compiler therefore maps a NO opportunity to an ASK at
1 - current NO ask while sizing maximum loss by the NO premium paid.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN

from .multimarket_cycle import PlannedExecutionIntent
from .multimarket_execution_journal import MultiMarketOrderDraft
from .opportunity_engine import Direction, Market


def _utc(value: datetime, *, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _money(value: Decimal, *, name: str) -> Decimal:
    if type(value) is not Decimal or not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be a positive finite Decimal")
    return value


def _text_decimal(value: Decimal) -> str:
    return format(value, "f")


@dataclass(frozen=True)
class EventExecutionQuote:
    ticker: str
    yes_ask_probability: Decimal
    no_ask_probability: Decimal
    captured_utc: datetime
    fractional_trading_enabled: bool
    max_count: Decimal = Decimal("100")

    def __post_init__(self) -> None:
        if not isinstance(self.ticker, str) or not self.ticker.strip() or len(self.ticker) > 160:
            raise ValueError("invalid event ticker")
        yes = _money(self.yes_ask_probability, name="YES ask")
        no = _money(self.no_ask_probability, name="NO ask")
        if yes >= 1 or no >= 1:
            raise ValueError("event asks must be strictly below 1")
        if yes + no < Decimal("0.90"):
            raise ValueError("event asks are implausibly crossed/incomplete")
        _utc(self.captured_utc, name="quote capture")
        if type(self.fractional_trading_enabled) is not bool:
            raise ValueError("fractional trading flag must be explicit")
        maximum = _money(self.max_count, name="event max count")
        if maximum > Decimal("100"):
            raise ValueError("event compiler count cap may not exceed router cap")


def _require_intent(intent: PlannedExecutionIntent) -> None:
    if not isinstance(intent, PlannedExecutionIntent):
        raise TypeError("PlannedExecutionIntent required")
    _money(intent.notional_usd, name="allocated notional")
    _money(intent.reserved_max_loss_usd, name="reserved max loss")
    if intent.reserved_max_loss_usd > intent.notional_usd:
        # Long equity/crypto max loss is normally below notional; event contracts
        # can lose the whole premium but never more than it.
        raise ValueError("reserved maximum loss cannot exceed allocated notional")


def compile_paper_draft(
    intent: PlannedExecutionIntent,
    *,
    as_of: datetime,
    event_quote: EventExecutionQuote | None = None,
    max_event_quote_age: timedelta = timedelta(seconds=30),
) -> MultiMarketOrderDraft:
    """Compile one planned entry intent into a provider-neutral durable draft.

    SHORT stock/crypto entry is intentionally rejected here until a separate
    instrument-level shortability and borrow/preflight compiler exists.
    """
    _require_intent(intent)
    now = _utc(as_of, name="as_of")

    if intent.market is Market.CRYPTO:
        if intent.direction is not Direction.LONG:
            raise PermissionError("crypto entry compiler is long-only PAPER")
        if event_quote is not None:
            raise ValueError("crypto intent cannot carry event quote")
        payload = {
            "symbol": intent.instrument,
            "side": "buy",
            "type": "market",
            "time_in_force": "gtc",
            "notional": _text_decimal(intent.notional_usd),
            "client_order_id": intent.client_intent_id,
        }
        return MultiMarketOrderDraft(
            intent.client_intent_id,
            "crypto",
            intent.instrument,
            intent.reserved_max_loss_usd,
            payload,
        )

    if intent.market is Market.US_EQUITY:
        if intent.direction is not Direction.LONG:
            raise PermissionError(
                "equity short entry requires separate shortability preflight"
            )
        if event_quote is not None:
            raise ValueError("equity intent cannot carry event quote")
        payload = {
            "symbol": intent.instrument,
            "side": "buy",
            "type": "market",
            "time_in_force": "day",
            "notional": _text_decimal(intent.notional_usd),
            "client_order_id": intent.client_intent_id,
        }
        return MultiMarketOrderDraft(
            intent.client_intent_id,
            "us_equity",
            intent.instrument,
            intent.reserved_max_loss_usd,
            payload,
        )

    if intent.market is Market.EVENT_CONTRACT:
        if intent.direction not in (Direction.YES, Direction.NO):
            raise PermissionError("event entry must be YES or NO")
        if event_quote is None:
            raise ValueError("fresh event execution quote required")
        if event_quote.ticker != intent.instrument:
            raise ValueError("event quote ticker differs from intent")
        captured = _utc(event_quote.captured_utc, name="quote capture")
        if captured > now:
            raise ValueError("future event quote forbidden")
        if max_event_quote_age <= timedelta(0) or now - captured > max_event_quote_age:
            raise ValueError("stale event quote cannot become execution draft")

        if intent.direction is Direction.YES:
            premium = event_quote.yes_ask_probability
            v2_side = "bid"
            v2_price = premium
        else:
            premium = event_quote.no_ask_probability
            v2_side = "ask"
            v2_price = Decimal("1") - premium

        # allocated_notional_usd is the maximum premium budget.  Kalshi V2
        # accepts fixed-point count; conservatively round DOWN and never exceed
        # the router's 100-contract cap.
        raw_count = intent.notional_usd / premium
        quantum = Decimal("0.01") if event_quote.fractional_trading_enabled else Decimal("1")
        count = raw_count.quantize(quantum, rounding=ROUND_DOWN)
        count = min(count, event_quote.max_count)
        if count <= 0:
            raise ValueError("allocated event notional cannot buy one minimum unit")
        actual_max_loss = count * premium
        if actual_max_loss > intent.reserved_max_loss_usd:
            # Risk sizing normally makes reserved risk equal to event notional.
            # If quote movement makes the planned count unsafe, reduce once.
            safe_raw = intent.reserved_max_loss_usd / premium
            count = safe_raw.quantize(quantum, rounding=ROUND_DOWN)
            count = min(count, event_quote.max_count)
            if count <= 0:
                raise ValueError("risk reserve cannot fund minimum event unit")
            actual_max_loss = count * premium
        if actual_max_loss > intent.reserved_max_loss_usd:
            raise AssertionError("event draft exceeds reserved maximum loss")

        payload = {
            "ticker": intent.instrument,
            "side": v2_side,
            "count": _text_decimal(count),
            "price": _text_decimal(v2_price),
            "time_in_force": "immediate_or_cancel",
            "self_trade_prevention_type": "taker_at_cross",
            "client_order_id": intent.client_intent_id,
        }
        return MultiMarketOrderDraft(
            intent.client_intent_id,
            "kalshi_event_contract",
            intent.instrument,
            actual_max_loss,
            payload,
        )

    raise ValueError("unsupported normalized market")

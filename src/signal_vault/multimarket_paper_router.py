"""Provider-neutral paper/demo execution routing for Signal Vault.

This module validates a durable cross-market execution draft AFTER the shared
risk governor has admitted the proposed risk. It still does not perform any
network request. It maps market lanes to paper/demo adapters and validates the
minimum safe provider payload contract.

Live trading is deliberately unavailable here.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping

from .multimarket_execution_journal import MultiMarketOrderDraft

ALPACA_PAPER_ROOT = "https://paper-api.alpaca.markets"
ALPACA_ORDER_PATH = "/v2/orders"

CRYPTO_PAPER_ACK = "I_ACKNOWLEDGE_ALPACA_CRYPTO_PAPER_ORDERS_ONLY"
EQUITY_PAPER_ACK = "I_ACKNOWLEDGE_ALPACA_EQUITY_PAPER_ORDERS_ONLY"
KALSHI_DEMO_ACK = "I_ACKNOWLEDGE_KALSHI_DEMO_ORDERS_ONLY"


@dataclass(frozen=True)
class PaperExecutionRoute:
    market_lane: str
    provider: str
    environment: str
    adapter: str
    endpoint: str | None
    payload: dict[str, str]
    required_acknowledgement: str
    live_trading_available: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "market_lane": self.market_lane,
            "provider": self.provider,
            "environment": self.environment,
            "adapter": self.adapter,
            "endpoint": self.endpoint,
            "payload": dict(self.payload),
            "required_acknowledgement": self.required_acknowledgement,
            "live_trading_available": self.live_trading_available,
            "automatic_submission": "DISABLED",
        }


def route_paper_execution(
    draft: MultiMarketOrderDraft,
    *,
    risk_assessment: Mapping[str, object],
    acknowledgement: str = "",
) -> PaperExecutionRoute:
    """Validate route eligibility; never perform a provider request."""
    _require_risk_receipt(draft, risk_assessment)

    if draft.market_lane == "crypto":
        payload = _validate_alpaca_crypto_payload(draft)
        required = CRYPTO_PAPER_ACK
        route = PaperExecutionRoute(
            market_lane="crypto",
            provider="alpaca",
            environment="paper",
            adapter="alpaca_crypto_paper",
            endpoint=ALPACA_PAPER_ROOT + ALPACA_ORDER_PATH,
            payload=payload,
            required_acknowledgement=required,
        )
    elif draft.market_lane == "us_equity":
        payload = _validate_alpaca_equity_payload(draft)
        required = EQUITY_PAPER_ACK
        route = PaperExecutionRoute(
            market_lane="us_equity",
            provider="alpaca",
            environment="paper",
            adapter="alpaca_equity_paper",
            endpoint=ALPACA_PAPER_ROOT + ALPACA_ORDER_PATH,
            payload=payload,
            required_acknowledgement=required,
        )
    elif draft.market_lane == "kalshi_event_contract":
        payload = _validate_kalshi_demo_payload(draft)
        required = KALSHI_DEMO_ACK
        route = PaperExecutionRoute(
            market_lane="kalshi_event_contract",
            provider="kalshi",
            environment="demo",
            adapter="kalshi_demo_signed_order_adapter_NOT_YET_IMPLEMENTED",
            endpoint=None,
            payload=payload,
            required_acknowledgement=required,
        )
    else:
        raise ValueError("unsupported market lane")

    if acknowledgement and acknowledgement != required:
        raise PermissionError("incorrect market-specific paper/demo acknowledgement")
    return route


def paper_submission_authorized(route: PaperExecutionRoute, acknowledgement: str) -> bool:
    if route.live_trading_available:
        raise ValueError("live-capable route is forbidden")
    return acknowledgement == route.required_acknowledgement


def _require_risk_receipt(
    draft: MultiMarketOrderDraft,
    receipt: Mapping[str, object],
) -> None:
    if (
        receipt.get("kind")
        != "CROSS_MARKET_RISK_ASSESSMENT_NOT_ORDER_AUTHORIZATION"
        or receipt.get("lane") != draft.market_lane
        or receipt.get("risk_admissible") is not True
        or receipt.get("assessment_is_not_trading_authorization") is not True
        or receipt.get("automatic_order_submission") != "DISABLED"
    ):
        raise PermissionError("matching admissible cross-market risk receipt required")


def _decimal(raw: str, *, name: str) -> Decimal:
    try:
        value = Decimal(raw)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid {name}") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError(f"invalid {name}")
    return value


def _base_order_fields(payload: Mapping[str, str]) -> dict[str, str]:
    data = dict(payload)
    required = {"symbol", "side", "type", "time_in_force", "client_order_id"}
    if not required.issubset(data):
        raise ValueError("missing required order fields")
    if data["side"] not in {"buy", "sell"}:
        raise ValueError("unsupported order side")
    if data["client_order_id"] == "":
        raise ValueError("client order id required")
    return data


def _validate_alpaca_crypto_payload(draft: MultiMarketOrderDraft) -> dict[str, str]:
    data = _base_order_fields(draft.payload)
    if data["symbol"] != draft.instrument or "/" not in data["symbol"]:
        raise ValueError("crypto draft instrument mismatch")
    if data["type"] not in {"market", "limit"}:
        raise ValueError("unsupported crypto paper order type")
    if data["time_in_force"] not in {"gtc", "ioc"}:
        raise ValueError("unsupported crypto paper time in force")
    if ("qty" in data) == ("notional" in data):
        raise ValueError("exactly one crypto quantity field required")
    if "qty" in data:
        _decimal(data["qty"], name="crypto qty")
    else:
        _decimal(data["notional"], name="crypto notional")
    allowed = {"symbol","side","type","time_in_force","client_order_id","qty","notional","limit_price"}
    if set(data) - allowed:
        raise ValueError("unexpected crypto paper payload field")
    if data["type"] == "limit":
        if "limit_price" not in data:
            raise ValueError("crypto limit order requires limit_price")
        _decimal(data["limit_price"], name="crypto limit price")
    elif "limit_price" in data:
        raise ValueError("market order cannot carry limit_price")
    return data


def _validate_alpaca_equity_payload(draft: MultiMarketOrderDraft) -> dict[str, str]:
    data = _base_order_fields(draft.payload)
    if data["symbol"] != draft.instrument or "/" in data["symbol"]:
        raise ValueError("equity draft instrument mismatch")
    if data["type"] != "market":
        raise ValueError("Phase 34 equity paper router allows market orders only")
    if data["time_in_force"] != "day":
        raise ValueError("fractional equity paper orders require day TIF")
    if ("qty" in data) == ("notional" in data):
        raise ValueError("exactly one equity quantity field required")
    if "qty" in data:
        qty = _decimal(data["qty"], name="equity qty")
        if qty.as_tuple().exponent < -9:
            raise ValueError("equity quantity exceeds 9 decimal places")
    else:
        notional = _decimal(data["notional"], name="equity notional")
        if notional.as_tuple().exponent < -9:
            raise ValueError("equity notional exceeds 9 decimal places")
    allowed = {"symbol","side","type","time_in_force","client_order_id","qty","notional"}
    if set(data) - allowed:
        raise ValueError("unexpected equity paper payload field")
    return data


def _validate_kalshi_demo_payload(draft: MultiMarketOrderDraft) -> dict[str, str]:
    data = dict(draft.payload)
    required = {"ticker", "side", "action", "count", "client_order_id"}
    if set(data) != required:
        raise ValueError("Kalshi demo draft requires exact bounded payload schema")
    if data["ticker"] != draft.instrument:
        raise ValueError("Kalshi draft instrument mismatch")
    if data["side"] not in {"yes", "no"}:
        raise ValueError("Kalshi side must be yes or no")
    if data["action"] not in {"buy", "sell"}:
        raise ValueError("Kalshi action must be buy or sell")
    count = _decimal(data["count"], name="Kalshi contract count")
    if count != count.to_integral_value():
        raise ValueError("Kalshi contract count must be an integer")
    if count > Decimal("100"):
        raise ValueError("Kalshi demo contract count exceeds Phase 34 bound")
    return data
